"""Chapter 20: how the owner component takes an action event in and what comes of it (P20.7, P20.8)."""
from common import write

# the kernel's decision (chapter 17, P17.10) for the grant's principal, as the step after the action's own checks
RETRY = {"view_unprovable", "qualification_unknown", "database_error"}
FINAL_REFUSALS = {"VERSION_CONFLICT", "TASK_NOT_PENDING", "SELF_APPROVAL", "NOT_ASSIGNEE", "PERMISSION_DENIED",
                  "NOT_QUALIFIED", "REVISION_CHANGED"}


def take(c):
    """The reference for one arriving action event: ignored (another owner's), refused (with the reason; audited; recorded
    on the grant or not; whether the holder gets an in-app intent), replayed (the first result of the same action),
    retry (nothing recorded: the event is nacked and redelivered) or executed."""
    out = {"answer": None, "reason": None, "audit": False, "record": False, "notify_holder": False}

    def refuse(reason, record=False, notify=False):
        return {**out, "answer": "refused", "reason": reason, "audit": True, "record": record, "notify_holder": notify}

    if not c["shape_ok"]:
        return refuse("malformed")
    if not c["audience_is_self"]:  # another owner's action: acknowledged silently
        return {**out, "answer": "ignored"}
    if not c["stream_is_source"]:
        return refuse("not_the_sender")
    if not c["grant_exists"]:
        return refuse("unknown_grant")
    if not c["principal_matches"]:
        return refuse("not_the_holder")
    if not c["action_allowed"]:
        return refuse("action_not_allowed")
    if c["prior"] == "same_action":  # the first result answers again, whatever it was
        return {**out, "answer": "replayed"}
    if c["prior"] == "other_action":
        return refuse("GRANT_USED", notify=True)
    if not c["clicked_in_time"] or not c["processed_in_time"]:
        return refuse("expired", record=True, notify=True)
    if c["security_version_newer"]:
        return refuse("GRANT_STALE", record=True, notify=True)
    d = c["decision"]
    if d in RETRY:
        return {**out, "answer": "retry", "reason": d}
    if d in FINAL_REFUSALS:
        return refuse(d, record=True, notify=True)
    return {**out, "answer": "executed", "record": True}


def channel_vectors():
    cases = []
    good = {"shape_ok": True, "audience_is_self": True, "stream_is_source": True, "grant_exists": True,
            "principal_matches": True, "action_allowed": True, "prior": "none", "clicked_in_time": True,
            "processed_in_time": True, "security_version_newer": False, "decision": "approved"}

    def add(cid, **change):
        c = {**good, **change}
        cases.append({"id": cid, "case": c, "expect": take(c)})

    add("executed")
    add("another-owner", audience_is_self=False)
    add("another-owner-not-the-sender", audience_is_self=False, stream_is_source=False)
    add("malformed", shape_ok=False)
    add("malformed-for-another-owner", shape_ok=False, audience_is_self=False)
    add("not-the-sender", stream_is_source=False)
    add("not-the-sender-unknown-grant", stream_is_source=False, grant_exists=False)
    add("unknown-grant", grant_exists=False)
    add("not-the-holder", principal_matches=False)
    add("not-the-holder-and-replay", principal_matches=False, prior="same_action")
    add("action-not-allowed", action_allowed=False)
    add("same-action-again", prior="same_action")
    add("same-action-again-after-expiry", prior="same_action", processed_in_time=False)
    add("other-action", prior="other_action")
    add("clicked-late", clicked_in_time=False)
    add("processed-late", processed_in_time=False)
    add("security-version-newer", security_version_newer=True)
    add("security-version-newer-and-late", security_version_newer=True, clicked_in_time=False)
    for d in sorted(RETRY):
        add("retry-" + d.replace("_", "-"), decision=d)
    for d in sorted(FINAL_REFUSALS):
        add("refused-" + d.lower().replace("_", "-"), decision=d)
    write("channel-action", ["P20.7", "P20.8"],
          "所属组件怎样收下一个渠道成员的动作事件、结果是什么。case：shape_ok 是载荷是否合 `schemas/channel/action.v1`；"
          "audience_is_self 是受众是不是本组件；stream_is_source 是事件所在的流属于配置的渠道成员、信封的来源与载荷的渠道成员都等于它；"
          "grant_exists 是动作授权在本组件；principal_matches 是事件的主体等于授权绑定的主体；action_allowed 是动作在授权允许的动作里；"
          "prior 是授权上已记的结果（none、same_action：同一动作已有最终结果、other_action：另一动作已有最终结果）；clicked_in_time 是点击的时刻不晚于授权的到期，"
          "processed_in_time 是处理的时刻不晚于到期加 1 小时；security_version_newer 是主体此刻的安全版本大于授权记下的；decision 是第 17 章对授权的主体作决定的结果"
          "（approved，或拒绝的原因，或可重试的 view_unprovable、qualification_unknown、database_error）。expect：answer 是 ignored（别的所属组件的，静默确认）、"
          "refused、replayed（答第一次的结果）、retry（什么也不记，否认事件、重投）或 executed；reason 是拒绝或重试的原因；audit 是写不写安全审计；"
          "record 是把结果记在授权上（同一授权的后续到达按它答）；notify_holder 是给授权的主体发一条站内意图说明没执行。核对按 case 的字段顺序，第一个不满足的决定结果。",
          cases, {"case": "到达时的情形", "expect": "结果"})
