"""Chapter 18: how the notification component takes an intent in (P18.3, P18.6, P18.7, P18.8, P18.9) and what one
recipient's delivery comes to (P18.3, P18.6, the component's preferences)."""
from common import write

MANDATORY = {"security_alert", "legal_notice"}
CATEGORIES = ["approval_task", "due_reminder", "security_alert", "legal_notice", "external_comm", "marketing"]
DEFAULT_OFF = {"marketing"}


def admit(c):
    """The reference for one arriving intent: refused (with the reason), a duplicate, stale (an older sequence of its
    merge key), or accepted; whether it supersedes the earlier intents of its merge key, and whether it is delivered."""
    out = {"answer": None, "supersedes": False, "delivers": False}
    if not c["shape_ok"]:  # first: a payload off the contract has no sender to trust
        return {**out, "answer": "malformed"}
    if not c["sender_is_source"]:
        return {**out, "answer": "not_the_sender"}
    if c["category"] not in CATEGORIES:
        return {**out, "answer": "unknown_category"}
    if c["kind"] == "deliver" and not c["expires_after_occurred"]:
        return {**out, "answer": "malformed"}
    if c["seen"]:
        return {**out, "answer": "duplicate"}
    if c["collapse_seq"] is not None:
        if c["max_seq"] is not None and c["collapse_seq"] <= c["max_seq"]:
            return {**out, "answer": "stale"}
        out["supersedes"] = True
    return {**out, "answer": "accepted", "delivers": c["kind"] == "deliver"}


def route(c):
    """The reference for one principal on one channel (in_app, or an external one, chapter 20): written (in-app),
    pending (an external delivery to hand over), preference_off or expired."""
    if c["category"] in MANDATORY and c["channel"] == "in_app":  # written even when expired: in-app is the fallback
        return "written"
    if c["expired"]:
        return "expired"
    on = c["preference"] == "on" or (c["preference"] == "unset" and c["category"] not in DEFAULT_OFF)
    if not on:
        return "preference_off"
    return "written" if c["channel"] == "in_app" else "pending"


def notification_vectors():
    cases = []
    good = {"kind": "deliver", "sender_is_source": True, "shape_ok": True, "category": "approval_task",
            "expires_after_occurred": True, "seen": False, "collapse_seq": None, "max_seq": None}

    def add(cid, **change):
        c = {**good, **change}
        cases.append({"id": "admit-" + cid, "case": {"step": "admit", **c}, "expect": admit(c)})

    add("plain")
    add("not-the-sender", sender_is_source=False)
    add("not-the-sender-and-malformed", sender_is_source=False, shape_ok=False)
    add("malformed", shape_ok=False)
    add("unknown-category", category="newsletter")
    add("unknown-category-and-malformed", category="newsletter", shape_ok=False)
    add("expires-not-after-occurred", expires_after_occurred=False)
    add("withdraw-has-no-expiry", kind="withdraw", expires_after_occurred=False, collapse_seq=3, max_seq=2)
    add("duplicate", seen=True)
    add("duplicate-of-a-stale-one", seen=True, collapse_seq=1, max_seq=5)
    add("first-of-its-key", collapse_seq=1)
    add("newer-of-its-key", collapse_seq=4, max_seq=3)
    add("older-of-its-key", collapse_seq=2, max_seq=3)
    add("same-seq-of-its-key", collapse_seq=3, max_seq=3)
    add("withdraw-newer", kind="withdraw", collapse_seq=5, max_seq=4)
    add("withdraw-first", kind="withdraw", collapse_seq=5)
    add("withdraw-older", kind="withdraw", collapse_seq=3, max_seq=4)
    add("security-alert", category="security_alert")

    def rt(cid, **c):
        case = {"category": "approval_task", "channel": "in_app", "preference": "unset", "expired": False, **c}
        cases.append({"id": "route-" + cid, "case": {"step": "route", **case}, "expect": {"result": route(case)}})

    for cat in CATEGORIES:
        for pref in ["unset", "on", "off"]:
            rt(f"{cat}-{pref}", category=cat, preference=pref)
            rt(f"{cat}-{pref}-external", category=cat, preference=pref, channel="external")
    rt("expired", expired=True)
    rt("expired-mandatory", category="security_alert", expired=True)
    rt("expired-mandatory-external", category="security_alert", expired=True, channel="external")
    rt("expired-off", preference="off", expired=True)
    write("notification-intent", ["P18.3", "P18.6", "P18.7", "P18.8", "P18.9", "P20.4"],
          "通知组件怎样收下一个意图（step=admit），与一个主体在一个渠道上的投递结果（step=route）。admit 的 case：kind 是 "
          "deliver 或 withdraw；shape_ok 是载荷是否合 schema（类别另算）；sender_is_source 是载荷里的发送方与信封的来源是否都等于意图所在的流的属主组件；category "
          "是类别（可能不在目录里）；expires_after_occurred 是到期是否晚于发生（撤回意图没有到期，不查）；seen 是同一“发送方 + 意图身份”"
          "是否已经收过；collapse_seq 是合并序号（null：没有合并键），max_seq 是这个合并键见过的最大序号（null：没见过）。expect：answer "
          "是 accepted、duplicate、stale（不大于见过的最大序号，作废）或拒收的原因（按 P18.8 的顺序：malformed、not_the_sender、"
          "unknown_category，然后是到期不晚于发生的 malformed）；supersedes 是否取代这个合并键之前的意图与站内消息；delivers 是否投递。"
          "route 的 case：category、channel（in_app 或 external：配置的外部渠道，第 20 章）、preference（unset、on、off：收件人对这个类别 × 渠道的偏好）、"
          "expired（到期已过）；expect 的 result 是 written（站内写入）、pending（外部投递待交出）、preference_off 或 expired。必须送达的类别"
          "（security_alert、legal_notice）的站内不看偏好、到期也照写；它们的外部渠道与别的类别一样看偏好与到期（P20.4）；没有偏好时 "
          "marketing 默认关，其余默认开。",
          cases, {"case": "到达时的情形", "expect": "结果"})
