"""Chapter 09: the watermark source's decision tables (P9.15, P9.20, P9.22-P9.24, P9.26, P9.28): the source's check of
the row at a consumer's contiguous position, what a consumer does with a pull's answer, which epoch it adopts, the
watermark from its partitions, and the judgement (protocol 02 of the assembly project, steps 1, 4, 6, 8-10)."""
from common import write


def epoch_key(e):
    g, t = e.split(".")
    return int(g), int(t)


# ---------------------------------------------------------------------------------------------- P9.15


def pull_check(source, req):
    """The source's check of one partition: ok, echo_only, beyond_retention or rollback_detected."""
    pos = req.get("position")
    if pos is None or pos["impl"] != source["impl"] or pos["epoch"] != source["epoch"]:
        return "echo_only"
    if pos["seq"] > source["counter"]:
        return "rollback_detected"
    row = source["rows"].get(str(pos["seq"]))
    if row is None:
        return "beyond_retention"
    return "ok" if row == req["row"] else "rollback_detected"


def pull_check_vectors():
    rows = {"7": {"record": {"record_id": "r1", "version": 3, "digest": "d-r1-3"}}, "8": {"echo_nonce": "n8"},
            "9": {"record": {"record_id": "r2", "version": 1, "digest": "d-r2-1"}}}
    src = {"impl": "i1", "epoch": "1.1", "counter": 9, "rows": rows}

    def at(seq, row, impl="i1", epoch="1.1"):
        return {"position": {"impl": impl, "epoch": epoch, "seq": seq}, "row": row}

    r1 = rows["7"]
    cases = [
        ("echo-only", {}),
        ("the-row-matches", at(7, r1)),
        ("an-echo-matches", at(8, {"echo_nonce": "n8"})),
        ("at-the-counter", at(9, rows["9"])),
        ("another-version-at-the-position", at(7, {"record": {"record_id": "r1", "version": 4, "digest": "d-r1-4"}})),
        ("same-version-another-digest", at(7, {"record": {"record_id": "r1", "version": 3, "digest": "other"}})),
        ("another-record", at(7, {"record": {"record_id": "rX", "version": 3, "digest": "d-r1-3"}})),
        ("another-echo", at(8, {"echo_nonce": "n-other"})),
        ("an-echo-where-a-record-is", at(7, {"echo_nonce": "n8"})),
        ("past-the-counter", at(12, {"echo_nonce": "n12"})),
        ("purged-by-the-retention", at(3, {"record": {"record_id": "r0", "version": 1, "digest": "d-r0-1"}})),
        ("another-epoch", at(7, r1, epoch="1.0")),
        ("a-larger-epoch-than-the-source", at(7, r1, epoch="2.1")),
        ("another-implementation-instance", at(7, r1, impl="i0")),
    ]
    write("watermark-pull-check", ["P9.15"],
          "水位来源核对消费者连续位置上的行（装配项目协议 02 第 1 步）：source 是来源这个分区当前的实现实例、纪元、计数与仍在的发件行"
          "（rows 按序号，值是行身份：回声的随机数，或记录身份、版本与行摘要）；request 是消费者带来的位置与行身份（没有位置是“只要回声”）；"
          "expect 是 ok（通过）、echo_only（不核对，只写回声）、beyond_retention 或 rollback_detected（需要完整快照与原因）。",
          [{"id": cid, "source": src, "request": req, "expect": pull_check(src, req)} for cid, req in cases],
          {"source": "来源这个分区", "request": "消费者的位置与行身份", "expect": "核对的结果"})


# ---------------------------------------------------------------------------------------------- P9.22, P9.28


def pull_outcome(consumer, resp):
    """What a consumer does with one partition of a pull answered by the adopted instance and epoch."""
    if resp.get("unreachable"):
        return "hold"
    need = resp.get("need_snapshot")
    if need == "beyond_retention":
        return "realign"
    if need == "rollback_detected":
        return "stall"
    if consumer.get("requested") is not None and resp["echo_seq"] < consumer["requested"]:
        return "stall"
    return "apply_to_echo"


def pull_outcome_vectors():
    c = {"requested": 40, "contiguous": 40}
    cases = [
        ("the-check-passed", c, {"echo_seq": 45}),
        ("nothing-new-but-the-echo", c, {"echo_seq": 41}),
        ("echo-only-after-alignment", {"requested": None, "contiguous": None}, {"echo_seq": 12}),
        ("the-stream-moved-past-the-echo-meanwhile", {"requested": 40, "contiguous": 47}, {"echo_seq": 45}),
        ("beyond-the-retention", c, {"need_snapshot": "beyond_retention"}),
        ("the-row-was-replaced", c, {"need_snapshot": "rollback_detected"}),
        ("the-echo-below-the-contiguous-position", c, {"echo_seq": 30}),
        ("the-source-unreachable", c, {"unreachable": True}),
    ]
    write("watermark-pull-outcome", ["P9.22", "P9.28"],
          "消费者对一个分区的补取响应怎样处理（装配项目协议 02“补取的时序与失败分支”与第 6 步的绊线），响应来自已采用的实现实例与纪元"
          "（别的纪元先按 watermark-epoch）：consumer.requested 是这次请求带的位置（null：只要回声），contiguous 是此刻已记录的连续位置"
          "（响应在路上时流可能已经推过回声，所以不拿它比较）；response 是"
          "回声的位置、需要完整快照的原因，或 unreachable（来源不可达、响应丢失）；expect：apply_to_echo（按位置应用到回声，水位 = m_p）、"
          "realign（完整重新取回，不告警）、stall（来源转 stalled、告警、完整重新取回，水位等采用更大的纪元）、hold（水位不动）。",
          [{"id": cid, "consumer": con, "response": r, "expect": pull_outcome(con, r)} for cid, con, r in cases],
          {"consumer": "这次请求带的位置与此刻的连续位置", "response": "补取响应", "expect": "处理"})


# ---------------------------------------------------------------------------------------------- P9.26


def epoch_decision(adopted, resp):
    """Which declared epoch a consumer uses: establish, use, adopt, ignore, stall, block or discard (alert)."""
    if resp["deployment"] != adopted["deployment"]:
        return "block"
    if adopted.get("impl") is None:  # the first contact, or after an environment copy cleared it (P9.26)
        return "establish" if resp["primary"] else "discard"
    if resp["impl"] != adopted["impl"]:
        return "block"
    if resp["primary"]:
        bigger = epoch_key(resp["epoch"]) > epoch_key(adopted["epoch"])
        gen_bigger = epoch_key(resp["epoch"])[0] > epoch_key(adopted["epoch"])[0]
        if resp["system_id"] != adopted["system_id"] and not gen_bigger:
            return "stall"
        if bigger:
            return "adopt"
        if epoch_key(resp["epoch"]) < epoch_key(adopted["epoch"]):
            return "ignore"
        return "use"
    same = resp["system_id"] == adopted["system_id"] and resp["epoch"] == adopted["epoch"]
    if not same or resp.get("purpose") in ("adopt", "align"):
        return "discard"
    return "use"


def epoch_vectors():
    a = {"deployment": "d1", "impl": "i1", "system_id": "s1", "epoch": "3.2"}

    def r(**kw):
        return {"deployment": "d1", "impl": "i1", "system_id": "s1", "epoch": "3.2", "primary": True, **kw}

    cases = [
        ("the-adopted-epoch", r()),
        ("a-failover-larger-timeline", r(epoch="3.3")),
        ("a-recovery-larger-generation", r(epoch="4.1")),
        ("a-major-upgrade-new-system-larger-generation", r(system_id="s2", epoch="4.1")),
        ("a-late-old-response", r(epoch="3.1")),
        ("an-older-generation", r(epoch="2.9")),
        ("a-restore-without-advancing-the-generation", r(system_id="s2", epoch="3.2")),
        ("a-new-system-and-a-larger-timeline-only", r(system_id="s2", epoch="3.3")),
        ("another-deployment", r(deployment="d2", epoch="9.1")),
        ("an-unregistered-implementation-instance", r(impl="i9", epoch="9.1")),
        ("a-replica-in-step", r(primary=False)),
        ("a-replica-behind-on-the-timeline", r(primary=False, epoch="3.1")),
        ("a-replica-of-another-system", r(primary=False, system_id="s2")),
        ("a-replica-answering-an-alignment-read", r(primary=False, purpose="align")),
        ("a-replica-declaring-a-larger-epoch", r(primary=False, epoch="4.1")),
    ]
    first = {"deployment": "d1", "impl": None, "system_id": None, "epoch": None}
    firsts = [("first-contact", r(impl="i7", system_id="s7", epoch="5.1")),
              ("first-contact-from-a-replica", r(impl="i7", primary=False)),
              ("first-contact-from-another-deployment", r(deployment="d2", impl="i7"))]
    write("watermark-epoch", ["P9.26"],
          "消费者对一个响应声明的来源身份怎样处理（装配项目协议 02 第 10 步与接收规则的前几行；来源更换实现的登记随 member-switching）："
          "adopted 是已采用的部署身份、实现实例、系统标识与纪元（<部署恢复代次>.<时间线>，按两段的数值比较；实现实例为 null 是第一次）；response 是响应的声明，"
          "primary 表示主库作答，purpose 是副本响应的用途；expect：establish（第一次：建立已采用的实现实例、系统标识与纪元，进入对齐）、use（照常使用）、adopt（采用：作废水位与连续位置，推进对齐代次，"
          "本次内容丢弃，进入对齐）、ignore（更小的纪元）、stall（来源转 stalled）、block（来源转 blocked）、discard（丢弃并告警）。",
          [{"id": cid, "adopted": a, "response": resp, "expect": epoch_decision(a, resp)} for cid, resp in cases] +
          [{"id": cid, "adopted": first, "response": resp, "expect": epoch_decision(first, resp)} for cid, resp in firsts],
          {"adopted": "已采用的来源身份", "response": "响应的声明", "expect": "处理"})


# ---------------------------------------------------------------------------------------------- P9.20, P9.23


def watermark(state):
    """A source's watermark: the minimum over its partitions of the m_p of the last own echo within the contiguous
    range; null without one in some partition, or when the clock went back or the consumer's epoch changed."""
    if state["now"] < state["max_seen"] or state["consumer_epoch"] != state["recorded_epoch"]:
        return None
    marks = []
    for p in state["partitions"]:
        own = [e["m_p"] for e in p["echoes"] if e.get("recorded") and e["seq"] <= p["contiguous"]]
        if not own:
            return None
        marks.append(max(own))
    return min(marks) if marks else None


def watermark_vectors():
    def st(parts, now=1000, max_seen=990, consumer_epoch="1.1", recorded_epoch="1.1"):
        return {"now": now, "max_seen": max_seen, "consumer_epoch": consumer_epoch, "recorded_epoch": recorded_epoch,
                "partitions": parts}

    def part(contiguous, *echoes):
        return {"contiguous": contiguous, "echoes": [{"seq": s, "m_p": m, "recorded": o} for s, m, o in echoes]}

    cases = [
        ("one-partition", st([part(10, (10, 900, True))])),
        ("the-minimum-over-partitions", st([part(10, (10, 900, True)), part(7, (7, 880, True))])),
        ("the-last-own-echo-in-the-range", st([part(20, (10, 900, True), (18, 950, True))])),
        ("an-echo-past-a-gap-does-not-count", st([part(12, (10, 900, True), (15, 960, True))])),
        ("an-echo-past-a-redelivery-wait-does-not-count", st([part(14, (10, 900, True), (16, 970, True))])),
        ("another-consumers-echo-does-not-count", st([part(20, (10, 900, True), (18, 950, False))])),
        ("a-partition-without-an-own-echo", st([part(10, (10, 900, True)), part(5)])),
        ("only-other-consumers-echoes", st([part(10, (10, 900, False))])),
        ("the-clock-went-back", st([part(10, (10, 900, True))], now=980, max_seen=990)),
        ("the-consumers-epoch-changed", st([part(10, (10, 900, True))], consumer_epoch="2.1")),
        ("after-a-clock-reset-the-old-pulls-are-gone", st([part(10, (10, 900, False))], now=1000, max_seen=995)),
        ("after-a-clock-reset-a-new-pull", st([part(12, (10, 900, False), (12, 960, True))], now=1000, max_seen=995)),
    ]
    write("watermark-value", ["P9.20", "P9.23"],
          "一个来源的水位（装配项目协议 02 第 4、8 步）：partitions 是各分区的连续已应用位置与流上、补取里出现的回声（位置、这个消费者"
          "补取时记下的 m_p；recorded 表示它是这个消费者发起、补取记录仍在的：别人的回声、时钟回拨或纪元变化时删掉的补取都不是）；now 与 max_seen 是消费者主库的当前事务时间与观察到的最大值，"
          "consumer_epoch 与 recorded_epoch 是消费者库当前的纪元与记下的纪元；expect 是水位（m_p），null 为没有水位。",
          [{"id": cid, "state": s, "expect": watermark(s)} for cid, s in cases],
          {"state": "消费者的状态", "expect": "水位"})


# ---------------------------------------------------------------------------------------------- P9.24


def judge(q):
    """Protocol 02 step 9: usable, provably_absent or unprovable. basis last_applied (P9.34) asks by the last applied
    facts: a stalled source is judged by its rows too, and the watermark's age does not count."""
    applied = q["basis"] == "last_applied"
    if not q["watermark_source"]:
        return "query_the_source"
    if q["source_state"] not in (("aligned", "stalled") if applied else ("aligned",)):  # aligning, blocked, outside
        return "unprovable"
    if q["projection_state"] != "serving":  # aligning (a new projection), untrusted, or outside the table
        return "unprovable"
    if q["quarantined"]:
        return "unprovable"
    if not applied and (q["watermark"] is None or q["watermark"] < q["now"] - q["freshness"]):
        return "unprovable"
    row = q["row"]
    adopted = row is None or row.get("adopted", True)
    if row is not None and row["state"] == "complete" and adopted:
        return "usable"
    if row is None or (row["state"] == "tombstone" and adopted):
        return "provably_absent"
    return "unprovable"


def judge_vectors():
    def q(**kw):
        base = {"basis": "fresh", "watermark_source": True, "source_state": "aligned", "projection_state": "serving",
                "quarantined": False, "watermark": 950, "now": 1000, "freshness": 60,
                "row": {"state": "complete", "adopted": True}}
        return {**base, **kw}

    cases = [
        ("not-a-watermark-source", q(watermark_source=False)),
        ("fresh-and-complete", q()),
        ("exactly-at-the-freshness", q(watermark=940)),
        ("expired", q(watermark=939)),
        ("no-watermark", q(watermark=None)),
        ("the-source-aligning", q(source_state="aligning")),
        ("the-source-stalled", q(source_state="stalled")),
        ("the-source-blocked", q(source_state="blocked")),
        ("a-new-projection-aligning", q(projection_state="aligning")),
        ("an-untrusted-projection", q(projection_state="untrusted")),
        ("a-quarantined-subject", q(quarantined=True)),
        ("no-such-row", q(row=None)),
        ("a-tombstone", q(row={"state": "tombstone", "adopted": True})),
        ("an-incomplete-row", q(row={"state": "incomplete", "adopted": True})),
        ("a-row-of-an-older-epoch", q(row={"state": "complete", "adopted": False})),
        ("a-tombstone-of-an-older-epoch", q(row={"state": "tombstone", "adopted": False})),
        ("expired-and-no-row", q(watermark=900, row=None)),
        ("a-source-state-outside-the-table", q(source_state="unknown")),
        ("a-projection-state-outside-the-table", q(projection_state="unknown")),
        # P9.34: by the last applied facts
        ("applied-an-old-watermark", q(basis="last_applied", watermark=100)),
        ("applied-no-watermark", q(basis="last_applied", watermark=None)),
        ("applied-the-source-stalled", q(basis="last_applied", source_state="stalled", watermark=100)),
        ("applied-the-source-aligning", q(basis="last_applied", source_state="aligning")),
        ("applied-the-source-blocked", q(basis="last_applied", source_state="blocked")),
        ("applied-a-new-projection-aligning", q(basis="last_applied", projection_state="aligning")),
        ("applied-an-untrusted-projection", q(basis="last_applied", projection_state="untrusted")),
        ("applied-a-quarantined-subject", q(basis="last_applied", source_state="stalled", quarantined=True)),
        ("applied-no-such-row", q(basis="last_applied", watermark=100, row=None)),
        ("applied-a-tombstone", q(basis="last_applied", source_state="stalled", row={"state": "tombstone", "adopted": True})),
        ("applied-an-incomplete-row", q(basis="last_applied", row={"state": "incomplete", "adopted": True})),
        ("applied-a-row-of-an-older-epoch", q(basis="last_applied", source_state="stalled",
                                              row={"state": "complete", "adopted": False})),
        ("applied-a-source-state-outside-the-table", q(basis="last_applied", source_state="unknown")),
    ]
    write("watermark-judge", ["P9.24", "P9.34"],
          "能否依据本地投影做安全或资格判断（装配项目协议 02 第 9 步的判断表，按行序第一条命中）：basis 是问法，fresh 按声明的新鲜度（P9.24），"
          "last_applied 按最后已应用的事实（P9.34：来源 stalled 也按行判断，不看水位的年龄）；watermark_source 是来源是否声明为水位来源，"
          "source_state 与 projection_state 是来源的对齐状态与投影级状态（serving、aligning、untrusted），quarantined 是所问的主体与读到的行的主体有没有被隔离，"
          "watermark、now、freshness 是水位、消费者主库的当前事务时间与声明的新鲜度（秒），row 是读到的行（null 为没有；adopted 表示"
          "属于已采用的实现实例与纪元）；expect：usable、provably_absent、unprovable，或 query_the_source（不用投影，同步查询来源）。",
          [{"id": cid, "query": x, "expect": judge(x)} for cid, x in cases],
          {"query": "判断的输入", "expect": "结果"})


# ---------------------------------------------------------------------------------------------- P9.26


def source_state(cur, ev):
    """Protocol 02's alignment state table, without step 12's rows (registered next instance, retired, withdrawn):
    the next state and what is recorded. cur: state, confirmed, rollback (a cause of the alignment), stalled_gen and
    blocked_gen (the recovery generation when it entered), prior (the state before blocked). ev: kind, gen (the
    recovery generation the input declares), and for a confirmed correction whether the row check passed."""
    st, k, gen = cur["state"], ev["kind"], ev.get("gen")
    out = {"state": st, "confirmed": cur.get("confirmed", False), "rollback": cur.get("rollback", False),
           "stalled_gen": cur.get("stalled_gen"), "blocked_gen": cur.get("blocked_gen"), "prior": cur.get("prior")}
    if k == "environment_copy":
        return {**out, "state": "aligning", "rollback": False, "confirmed": False, "action": "clear_and_refetch"}
    if k == "foreign":  # an unregistered implementation instance, or another deployment
        if st == "blocked":
            return {**out, "action": "alert"}
        return {**out, "state": "blocked", "prior": st, "blocked_gen": gen, "action": "alert_and_hold"}
    if st == "blocked":
        if k == "operator_confirms":
            return {**out, "confirmed": True, "action": "record_confirmation"}
        if out["confirmed"] and k == "primary_response":
            if not ev["matches"]:
                return {**out, "confirmed": False, "action": "alert"}
            prior_stalled = out["prior"] == "stalled" and not (gen > (out["stalled_gen"] or 0))
            if prior_stalled:
                return {**out, "state": "stalled", "confirmed": False, "action": "refetch"}
            if ev.get("row_check") == "failed":
                return {**out, "state": "stalled", "confirmed": False, "rollback": True, "stalled_gen": gen,
                        "action": "refetch"}
            return {**out, "state": "aligning", "confirmed": False, "action": "row_check_then_refetch"}
        return {**out, "action": "hold"}
    if k == "rollback":  # the tripwire, or a primary's new system without a larger generation
        return {**out, "state": "stalled", "rollback": True, "stalled_gen": gen, "action": "refetch"}
    if st == "stalled":
        if k == "adopt_epoch" and gen > out["stalled_gen"]:
            return {**out, "state": "aligning", "action": "refetch"}
        return {**out, "action": "keep_refetching"}
    if k in ("adopt_epoch", "first_contact", "beyond_retention"):
        return {**out, "state": "aligning", "action": "refetch"}
    if st == "aligning" and k == "alignment_done":
        if out["rollback"] and not (gen > (out["stalled_gen"] or 0)):
            return {**out, "state": "stalled", "action": "alert"}
        return {**out, "state": "aligned", "rollback": False, "action": "watermark_from_echoes"}
    return {**out, "action": "alert"}


def source_state_vectors():
    def c(state, **kw):
        return {"state": state, **kw}

    cases = [
        ("first-contact", c("aligning"), {"kind": "first_contact", "gen": 3}),
        ("aligned-adopts-a-larger-epoch", c("aligned"), {"kind": "adopt_epoch", "gen": 3}),
        ("aligned-beyond-the-retention", c("aligned"), {"kind": "beyond_retention", "gen": 3}),
        ("aligning-done", c("aligning"), {"kind": "alignment_done", "gen": 3}),
        ("aligned-the-tripwire", c("aligned"), {"kind": "rollback", "gen": 3}),
        ("stalled-a-failover-only", c("stalled", rollback=True, stalled_gen=3), {"kind": "adopt_epoch", "gen": 3}),
        ("stalled-the-generation-advanced", c("stalled", rollback=True, stalled_gen=3), {"kind": "adopt_epoch", "gen": 4}),
        ("stalled-beyond-the-retention", c("stalled", rollback=True, stalled_gen=3), {"kind": "beyond_retention", "gen": 3}),
        ("stalled-refetch-done", c("stalled", rollback=True, stalled_gen=3), {"kind": "alignment_done", "gen": 3}),
        ("aligning-after-a-rollback-done-generation-advanced", c("aligning", rollback=True, stalled_gen=3),
         {"kind": "alignment_done", "gen": 4}),
        ("aligning-after-a-rollback-done-not-advanced", c("aligning", rollback=True, stalled_gen=3),
         {"kind": "alignment_done", "gen": 3}),
        ("aligned-a-foreign-response", c("aligned"), {"kind": "foreign", "gen": 3}),
        ("stalled-a-foreign-response", c("stalled", rollback=True, stalled_gen=3), {"kind": "foreign", "gen": 3}),
        ("blocked-again", c("blocked", prior="aligned", blocked_gen=3), {"kind": "foreign", "gen": 3}),
        ("blocked-any-other-input", c("blocked", prior="aligned", blocked_gen=3), {"kind": "primary_response",
                                                                                  "matches": True, "gen": 3}),
        ("blocked-the-operator-confirms", c("blocked", prior="aligned", blocked_gen=3), {"kind": "operator_confirms"}),
        ("confirmed-a-matching-response", c("blocked", confirmed=True, prior="aligned", blocked_gen=3),
         {"kind": "primary_response", "matches": True, "row_check": "passed", "gen": 3}),
        ("confirmed-the-row-check-fails", c("blocked", confirmed=True, prior="aligned", blocked_gen=3),
         {"kind": "primary_response", "matches": True, "row_check": "failed", "gen": 3}),
        ("confirmed-still-wrong", c("blocked", confirmed=True, prior="aligned", blocked_gen=3),
         {"kind": "primary_response", "matches": False, "gen": 3}),
        ("confirmed-was-stalled-not-advanced", c("blocked", confirmed=True, prior="stalled", rollback=True,
                                                 stalled_gen=3, blocked_gen=3),
         {"kind": "primary_response", "matches": True, "row_check": "passed", "gen": 3}),
        ("confirmed-was-stalled-advanced-meanwhile", c("blocked", confirmed=True, prior="stalled", rollback=True,
                                                       stalled_gen=3, blocked_gen=3),
         {"kind": "primary_response", "matches": True, "row_check": "passed", "gen": 4}),
        ("an-environment-copy", c("stalled", rollback=True, stalled_gen=3), {"kind": "environment_copy"}),
    ]
    write("watermark-source-state", ["P9.26"],
          "一个来源的对齐状态怎样迁移（装配项目协议 02 的对齐状态表，去掉第 12 步的几行）：current 是状态（aligned、aligning、stalled、"
          "blocked）、confirmed（blocked 的“已确认”）、rollback（对齐的起因有回退）、stalled_gen 与 blocked_gen（进入时的部署恢复代次）、"
          "prior（进入 blocked 前的状态）；event 是 first_contact、adopt_epoch（采用更大的纪元）、beyond_retention、rollback（绊线，或主库"
          "的系统标识不同而代次不更大）、foreign（没有登记的实现实例或别的部署）、operator_confirms、primary_response（matches：属于已采用的"
          "实例与部署、系统标识相同或不同而代次更大；row_check：保存的连续位置上的行核对）、alignment_done、environment_copy，gen 是输入"
          "声明的部署恢复代次；expect 是之后的这些字段与动作。",
          [{"id": cid, "current": cur, "event": ev, "expect": source_state(cur, ev)} for cid, cur, ev in cases],
          {"current": "来源此刻的状态", "event": "输入", "expect": "之后的状态与动作"})


def all_vectors():
    pull_check_vectors()
    pull_outcome_vectors()
    epoch_vectors()
    watermark_vectors()
    judge_vectors()
    source_state_vectors()
