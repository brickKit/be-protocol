"""Chapter 16: a reservation participant's branch transitions (P16.1-P16.8)."""
from common import write

ENDED = ("consumed", "released", "expired", "rejected", "cancelled")


def step(cur, cmd):
    """The reference: the state after, the answer, what happens to the resource, whether the branch changed."""
    st = None if cur is None else cur["state"]
    past = bool(cur and cur.get("past"))
    same = lambda: ("absent" if st is None else st, "ok", "none", False)  # noqa: E731
    if cmd == "query":
        return same()
    if cmd.startswith("hold"):
        if st is None:
            return ("held", "ok", "take", True) if cmd == "hold-enough" else ("rejected", "ok", "none", True)
        if st == "cancelled" or cmd == "hold-same":
            return same()
        return (st, "conflict", "none", False)
    if cmd == "confirm":
        if st == "held":
            return ("expired", "ok", "give_back", True) if past else ("committed", "ok", "none", True)
        return same()
    if cmd == "cancel":
        if st is None:
            return ("cancelled", "ok", "none", True)
        if st in ("held", "committed"):
            return ("released", "ok", "give_back", True)
        return same()
    if cmd == "expire":
        if st == "held" and past:
            return ("expired", "ok", "give_back", True)
        return same()
    # consumptions
    if cmd == "consume-used-same":
        return same()
    if cmd == "consume-used-other":
        return (st, "conflict", "none", False)
    if st is None:
        return ("absent", "refused:absent", "none", False)
    if st != "committed":
        return (st, "refused:not_committed", "none", False)
    if cmd == "consume-beyond":
        return (st, "refused:beyond_remaining", "none", False)
    return ("committed" if cmd == "consume-within" else "consumed", "ok", "consume", True)


def participant_vectors():
    currents = {"none": None, "held": {"state": "held"}, "held-past": {"state": "held", "past": True},
                "committed": {"state": "committed"}}
    for s in ENDED:
        currents[s] = {"state": s}
    cases = []
    for cname, cur in currents.items():
        cmds = ["query", "confirm", "cancel", "expire"]
        cmds += ["hold-enough", "hold-short"] if cur is None else ["hold-same", "hold-other"]
        cmds += ["consume-within", "consume-exact", "consume-beyond"]
        if cur is not None:
            cmds += ["consume-used-same", "consume-used-other"]
        for cmd in cmds:
            state, answer, resource, changed = step(cur, cmd)
            cases.append({"id": f"{cname}-{cmd}", "current": cur, "command": cmd,
                          "expect": {"state": state, "answer": answer, "resource": resource, "changed": changed}})
    write("reserve-participant", ["P16.1", "P16.2", "P16.3", "P16.4", "P16.5", "P16.6", "P16.7", "P16.8"],
          "预占参与方的分支迁移：current 是保存的分支（null 为没有；past 表示暂存期限已到）；command 是到达的命令："
          "query、confirm、cancel、expire（到期作业，在锁下重新判断）、hold-enough / hold-short（没有分支时，资源足够或不足）、"
          "hold-same / hold-other（已有分支时，内容摘要相同或不同）、consume-within / consume-exact / consume-beyond（新的消耗身份，"
          "消耗后还有剩余、正好消耗完、超出剩余）、consume-used-same / consume-used-other（用过的消耗身份，内容相同或不同）；"
          "expect 是之后的状态（absent：没有分支）、回答（ok、conflict、refused:<原因>，原因 absent、not_committed、beyond_remaining）、"
          "对资源做什么（take 占用、give_back 归还没消耗的部分、consume 消耗、none）与分支是否改变（版本加一并发分支事件）。",
          cases, {"current": "保存的分支", "command": "到达的命令", "expect": "结果"})
