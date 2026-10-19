"""Chapter 08 vectors for accepting a view verification answer (P8.11): recovery generation, member instance, and the
epoch and value of each security revision against what the component holds."""
from common import write

A, B = "authz-inst-a", "authz-inst-b"


def rev(domain, epoch, value, instance=A):
    return {"domain": domain, "epoch": epoch, "value": str(value), "instance": instance}


def epoch_key(e):
    gen, timeline = e.split(".")
    return int(gen), int(timeline)


def regressed(held, new):
    """A changed shard under the same recovery generation goes back when one of its domains has an earlier epoch, or
    the same epoch and a lower value, than the shard the component holds."""
    old = {r["domain"]: r for r in held}
    for r in new:
        o = old.get(r["domain"])
        if o is None:
            continue
        if epoch_key(r["epoch"]) < epoch_key(o["epoch"]):
            return True
        if r["epoch"] == o["epoch"] and int(r["value"]) < int(o["value"]):
            return True
    return False


def accept(held, answer):
    """The reference: held = {recovery, instance, shards: {name: {revisions, stopped}}}, answer = {recovery, shards}."""
    shards = {k: dict(v) for k, v in held["shards"].items()}
    views = {r["instance"] for a in answer["shards"] if a["status"] == "changed" for r in a["view"]["security_revisions"]}
    pinned = held["instance"]
    if (held["recovery"] is not None and answer["recovery"] < held["recovery"]) or \
            (pinned is not None and answer["instance"] != pinned) or views - {answer["instance"]}:
        return {"answer": "rollback", "instance": pinned,
                "shards": {k: "stopped" if s.get("stopped") else "suspended" for k, s in shards.items()}}
    out = {}
    if held["recovery"] is not None and answer["recovery"] > held["recovery"]:
        out = {k: "dropped" for k in shards}  # every older shard is void
        shards = {}
        newer = True
    else:
        newer = held["recovery"] is None
    for k, s in shards.items():
        out[k] = "stopped" if s.get("stopped") else "suspended" if s.get("suspended") else "kept"
    for a in answer["shards"]:
        k, s = a["shard"], shards.get(a["shard"])
        if a["status"] == "unchanged":
            if s is not None and not s.get("stopped"):
                out[k] = "renewed"
        elif a["status"] == "changed":
            if s is not None and s.get("stopped"):
                continue  # stays stopped until a higher recovery generation
            if not newer and s is not None and regressed(s["revisions"], a["view"]["security_revisions"]):
                out[k] = "stopped"
            else:
                out[k] = "replaced"
        # closed: not renewed, runs out on its own
    return {"answer": "accepted", "instance": answer["instance"], "shards": out}


def held_state(recovery, instance, **shards):
    return {"recovery": recovery, "instance": instance, "shards": shards}


def shard(*revisions, stopped=False, suspended=False):
    s = {"revisions": list(revisions)}
    if stopped:
        s["stopped"] = True
    if suspended:
        s["suspended"] = True
    return s


def answer(recovery, *shards, instance=A):
    return {"recovery": recovery, "instance": instance, "shards": list(shards)}


def changed(name, *revisions):
    return {"shard": name, "status": "changed", "view": {"security_revisions": list(revisions)}}


def status(name, st):
    return {"shard": name, "status": st}


def view_accept_vectors():
    le, org = "authz.security.legal_entity", "authz.security.org"
    h1 = held_state(1, A, s1=shard(rev(le, "1.1", 10)))
    scenarios = [
        ("start", "进程启动时没有视图：采用回答，记下成员实例",
         held_state(None, None), answer(1, changed("s1", rev(le, "1.1", 10)))),
        ("unchanged", "未变：续期", h1, answer(1, status("s1", "unchanged"))),
        ("unchanged-not-held", "对没有持有的分片答未变：不产生分片", h1, answer(1, status("s1", "unchanged"), status("s2", "unchanged"))),
        ("closed", "关闭：不续期，到期自然失效", h1, answer(1, status("s1", "closed"))),
        ("not-mentioned", "回答没有提到的分片：不续期", held_state(1, A, s1=shard(rev(le, "1.1", 10)), s2=shard(rev(org, "1.1", 3))),
         answer(1, status("s1", "unchanged"))),
        ("newer-value", "同一纪元、修订更高：换成新视图", h1, answer(1, changed("s1", rev(le, "1.1", 11)))),
        ("same-value", "同一纪元、修订相同（视图内容变了，例如能力）：换成新视图", h1, answer(1, changed("s1", rev(le, "1.1", 10)))),
        ("lower-value", "同一纪元、修订更低：判为回退，停用这个分片", h1, answer(1, changed("s1", rev(le, "1.1", 9)))),
        ("later-timeline", "纪元更晚（时间线变大）、数值更低：换成新视图", h1, answer(1, changed("s1", rev(le, "1.2", 2)))),
        ("later-generation", "纪元的恢复代次更大：换成新视图", h1, answer(1, changed("s1", rev(le, "2.1", 1)))),
        ("earlier-epoch", "纪元更早（未隔离的旧主库作答）：判为回退，停用这个分片",
         held_state(1, A, s1=shard(rev(le, "1.2", 5))), answer(1, changed("s1", rev(le, "1.1", 8)))),
        ("new-domain", "新视图多了一个依赖域：没有可比的旧值，换成新视图", h1,
         answer(1, changed("s1", rev(le, "1.1", 10), rev(org, "1.1", 1)))),
        ("one-domain-back", "两个依赖域里一个回退：停用这个分片",
         held_state(1, A, s1=shard(rev(le, "1.1", 10), rev(org, "1.1", 7))),
         answer(1, changed("s1", rev(le, "1.1", 12), rev(org, "1.1", 6)))),
        ("mixed", "一个分片回退、另一个前进：分别处理",
         held_state(1, A, s1=shard(rev(le, "1.1", 10)), s2=shard(rev(org, "1.1", 3))),
         answer(1, changed("s1", rev(le, "1.1", 9)), changed("s2", rev(org, "1.1", 4)))),
        ("recovery-lower", "恢复代次更低（旧成员从旧备份重启后作答）：整个回答判为回退，停用全部视图",
         held_state(2, A, s1=shard(rev(le, "2.1", 3))), answer(1, changed("s1", rev(le, "1.1", 50)))),
        ("recovery-higher", "恢复代次更高：旧分片全部作废，只用回答里的新视图，不比较修订",
         held_state(1, A, s1=shard(rev(le, "1.1", 10)), s2=shard(rev(org, "1.1", 3))),
         answer(2, changed("s1", rev(le, "2.1", 1)))),
        ("other-instance", "另一个成员实例作答（没有登记的成员切换）：整个回答判为回退", h1,
         answer(1, changed("s1", rev(le, "1.1", 11, B)), instance=B)),
        ("other-instance-unchanged", "另一个实例只答未变（例如从备份另建的环境内容相同）：仍判为回退，不续期", h1,
         answer(1, status("s1", "unchanged"), instance=B)),
        ("other-instance-higher", "另一个实例、恢复代次也更高：仍判为回退", h1,
         answer(2, changed("s1", rev(le, "2.1", 1, B)), instance=B)),
        ("view-instance-mismatch", "视图里的修订带着另一个实例：判为回退", held_state(None, None),
         answer(1, changed("s1", rev(le, "1.1", 1)), changed("s2", rev(org, "1.1", 1, B)))),
        ("stopped-stays", "已因回退停用的分片：同一恢复代次的新视图不解除，只等更高的恢复代次",
         held_state(1, A, s1=shard(rev(le, "1.1", 10), stopped=True)), answer(1, changed("s1", rev(le, "1.1", 11)))),
        ("stopped-unchanged", "已停用的分片答未变：不续期", held_state(1, A, s1=shard(rev(le, "1.1", 10), stopped=True)),
         answer(1, status("s1", "unchanged"))),
        ("suspended-renewed", "整个回答被判回退后暂停的分片：下一个被采用的回答续期它，即恢复使用",
         held_state(1, A, s1=shard(rev(le, "1.1", 10), suspended=True)), answer(1, status("s1", "unchanged"))),
        ("suspended-kept", "暂停的分片没有被续期：仍暂停", held_state(1, A, s1=shard(rev(le, "1.1", 10), suspended=True),
                                                         s2=shard(rev(org, "1.1", 3))), answer(1, status("s2", "unchanged"))),
        ("suspended-lower", "暂停的分片收到更低的修订：判为回退、停用", held_state(1, A, s1=shard(rev(le, "1.1", 10), suspended=True)),
         answer(1, changed("s1", rev(le, "1.1", 9)))),
        ("stopped-recovery-higher", "已停用的分片在恢复代次推进后：作废，采用新视图",
         held_state(1, A, s1=shard(rev(le, "1.1", 10), stopped=True)), answer(2, changed("s1", rev(le, "2.1", 1)))),
    ]
    cases = [{"id": cid, "note": note, "held": h, "answer": a, "expect": accept(h, a)} for cid, note, h, a in scenarios]
    write("view-accept", ["P8.11"],
          "组件收到核验回答之后怎样处理（随机数已核对；安全 03 的接受表）。held 是组件持有的：恢复代次（null 表示进程启动后"
          "还没有视图）、已记下的成员实例、各分片的安全修订，以及是否停用（stopped）或暂停（suspended）。answer 是回答的恢复代次、作答的成员实例（instance）与各分片（status："
          "unchanged、changed、closed；changed 带新视图的 security_revisions，每个 RevisionRef 带 instance 与 epoch）。纪元"
          "写作“部署恢复代次.时间线”，按两个整数的字典序比较。expect.answer：accepted 或 rollback（整个回答不采用，"
          "停用全部视图并告警）；expect.instance：之后记下的成员实例；expect.shards：每个分片的结果——renewed（续期）、"
          "replaced（换成新视图并续期）、kept（不续期，到期自然失效）、suspended（整个回答判为回退时，持有的分片暂停使用、修订"
          "留作比较；下一个被采用的回答续期或换掉它即恢复）、stopped（判为回退，停用并告警；只在更高的恢复代次"
          "之后解除）、dropped（恢复代次更高，旧分片作废）。判断的先后：恢复代次更低、作答的成员实例与记下的不同、或新视图"
          "的修订带着别的实例 → rollback；恢复代次更高 → 旧分片全部作废、不比较修订；同一恢复代次 → 逐分片、逐依赖域"
          "比较：纪元更早、或同一纪元数值更低 → stopped。",
          cases, {"held": "组件持有的状态", "answer": "核验回答（摘要与视图内容从略）", "expect": "处理之后的结果"})
