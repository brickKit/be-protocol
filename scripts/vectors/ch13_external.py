"""Chapter 13: external commands (P13.2-P13.8): the state transitions, the resend decision after a "not found" query,
and the resend deadline. A reference model of the assembly project's protocol 10 tables, first matching row wins."""
from datetime import datetime, timedelta, timezone

from ch08_canonical import digest
from common import write

TERMINAL = ("succeeded", "failed", "rejected")
WARN_AFTER, MANUAL_AFTER = timedelta(hours=1), timedelta(hours=24)


def t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def margin(window):
    return max(window / 10, timedelta(hours=1))


def deadline(cmd, caps):
    """P13.7: the resend deadline, or None (no dedupe, or no send that may have reached the external system)."""
    if not caps.get("dedupe_window"):
        return None
    first = cmd.get("first_reached_at")
    base = (cmd.get("last_reached_at") or first) if caps.get("window_from") == "last_use" else first
    if not base:
        return None
    w = timedelta(seconds=caps["dedupe_window"])
    return iso(t(base) + w - margin(w))


def not_found(cmd, caps, now):
    """P13.6: a query answered "not found": resend only when the earlier request can no longer land."""
    d = deadline(cmd, caps)
    if d and t(now) <= t(d):
        return "resend", "the external system deduplicates and the deadline has not passed"
    if cmd.get("expires_at") and t(now) > t(cmd["expires_at"]):
        return "resend", "the request's expiry has passed"
    latest = max((x for x in (cmd.get("last_reached_at"), cmd.get("unrecorded_until")) if x), key=t, default=None)
    if caps.get("max_processing") and latest and t(now) - t(latest) > timedelta(seconds=caps["max_processing"]):
        return "resend", "the longest processing time has passed"
    return "manual", "the earlier request may still land"


def step(cmd, event, caps, now):
    """One event on a command (P13.3-P13.8): the next state and why. Terminal states absorb everything."""
    s, kind = cmd["state"], event["kind"]
    if s in TERMINAL:
        return s, "a terminal state absorbs every later result"
    d = cmd.get("resend_deadline")
    if kind == "claim" and s in ("prepared", "retry_wait"):
        if d and t(now) > t(d):
            return "unknown", "claimed past the resend deadline"
        return "sending", "claimed: the transition commits before the send"
    if kind == "before_send" and s == "sending":
        if d and t(now) > t(d):
            return "unknown", "past the resend deadline before the send: not sent"
        return "sending", "sent"
    if kind == "lease_lost" and s == "sending":
        return "unknown", "the claimant is gone: whether it sent is not known"
    if kind == "send_result" and s == "sending":
        return {"not_reached": ("retry_wait", "certainly not processed: backoff and send again"),
                "maybe_reached": ("unknown", "may have been processed: query first"),
                "accepted": ("accepted", "accepted, not final"),
                "succeeded": ("succeeded", "final"), "failed": ("failed", "final"),
                "rejected": ("rejected", "refused for good")}[event["result"]]
    if kind == "query" and s in ("unknown", "accepted"):
        r = event["result"]
        if r == "found":
            ext = event["external_state"]
            return (ext, "the external record") if ext in TERMINAL + ("accepted",) else (s, "the external record, not final")
        if r == "unavailable":
            since = cmd.get("unknown_since") if s == "unknown" else cmd.get("accepted_at")
            if since and t(now) - t(since) > MANUAL_AFTER:
                return "manual", "no answer within the manual limit"
            return s, "the query is unavailable: backoff"
        if r == "not_found" and s == "unknown":
            action, why = not_found(cmd, caps, now)
            return ("sending", why) if action == "resend" else ("manual", why)
    if kind == "finality_passed" and s == "accepted":
        if caps.get("query"):
            return "accepted", "past the finality limit: query"
        since = cmd.get("accepted_at")
        if since and t(now) - t(since) > MANUAL_AFTER:
            return "manual", "no query and past the manual limit"
        return "accepted", "waiting for the callback or the reconciliation"
    if kind == "registered" and s == "manual":
        return event["result"], "registered by a person, with its grounds"
    return s, "not a transition of the table: unchanged, logged"


DEDUPE_24H = {"dedupe_window": 86400, "window_from": "first_use", "query": True}
NO_DEDUPE = {"query": True}


def external_vectors():
    cases = []

    def case(cid, cmd, event, caps, now, want_state, ei=None):
        got, why = step(cmd, event, caps, now)
        assert got == want_state, (cid, got, why)
        c = {"id": cid, "input": {"command": cmd, "event": event, "capabilities": caps, "now": now},
             "expected": {"state": got, "reason": why}}
        if ei:
            c["description"] = ei
        cases.append(c)

    t0 = "2026-11-05T10:00:00.000000Z"
    sent = {"state": "sending", "first_reached_at": t0, "last_reached_at": t0}
    case("ei01-read-timeout", {"state": "sending"}, {"kind": "send_result", "result": "maybe_reached"}, NO_DEDUPE, t0,
         "unknown", "EI01: a read timeout is unknown, queried first")
    case("connection-failed", {"state": "sending"}, {"kind": "send_result", "result": "not_reached"}, NO_DEDUPE, t0,
         "retry_wait")
    case("accepted", {"state": "sending"}, {"kind": "send_result", "result": "accepted"}, NO_DEDUPE, t0, "accepted",
         "EI12: accepted is not paid")
    case("rejected", {"state": "sending"}, {"kind": "send_result", "result": "rejected"}, NO_DEDUPE, t0, "rejected")
    unk = dict(sent, state="unknown", unknown_since=t0)
    case("ei02-query-unavailable", unk, {"kind": "query", "result": "unavailable"}, NO_DEDUPE,
         "2026-11-05T11:00:00.000000Z", "unknown", "EI02: the query unavailable: backoff")
    case("ei02-past-the-manual-limit", unk, {"kind": "query", "result": "unavailable"}, NO_DEDUPE,
         "2026-11-06T10:00:01.000000Z", "manual", "EI02: past the manual limit")
    case("ei03-not-found-no-dedupe", unk, {"kind": "query", "result": "not_found"}, NO_DEDUPE,
         "2026-11-05T10:05:00.000000Z", "manual", "EI03: not found, no dedupe, no expiry, no longest processing time")
    unk24 = dict(unk, resend_deadline=deadline(unk, DEDUPE_24H))
    case("ei04-not-found-dedupe", unk24, {"kind": "query", "result": "not_found"}, DEDUPE_24H,
         "2026-11-05T12:00:00.000000Z", "sending", "EI04: not found, the external system deduplicates: same reference")
    case("ei36-not-found-past-the-window", unk24, {"kind": "query", "result": "not_found"}, DEDUPE_24H,
         "2026-11-08T10:00:00.000000Z", "manual", "EI36: the dedupe window passed: not by dedupe")
    resent = dict(unk, last_reached_at="2026-11-06T09:00:00.000000Z")
    resent["resend_deadline"] = deadline(resent, DEDUPE_24H)
    case("ei39-first-use-window", resent, {"kind": "query", "result": "not_found"}, DEDUPE_24H,
         "2026-11-06T16:00:00.000000Z", "manual", "EI39: counted from the first use, 30 h after it")
    last_use = dict(DEDUPE_24H, window_from="last_use")
    resent_last = dict(resent, resend_deadline=deadline(resent, last_use))
    case("last-use-window", resent_last, {"kind": "query", "result": "not_found"}, last_use,
         "2026-11-06T16:00:00.000000Z", "sending", "a last-use window counts from the latest send")
    case("expiry-passed", dict(unk, expires_at="2026-11-05T10:30:00.000000Z"), {"kind": "query", "result": "not_found"},
         NO_DEDUPE, "2026-11-05T11:00:00.000000Z", "sending")
    case("longest-processing-passed", unk, {"kind": "query", "result": "not_found"}, dict(NO_DEDUPE, max_processing=3600),
         "2026-11-05T11:00:01.000000Z", "sending")
    case("longest-processing-unrecorded", dict(unk, unrecorded_until="2026-11-05T10:30:00.000000Z"),
         {"kind": "query", "result": "not_found"}, dict(NO_DEDUPE, max_processing=3600), "2026-11-05T11:00:01.000000Z",
         "manual", "a full recovery: sends until the failure may be unrecorded; the longest processing time counts from it")
    case("found-succeeded", unk, {"kind": "query", "result": "found", "external_state": "succeeded"}, NO_DEDUPE, t0,
         "succeeded")
    case("ei08-late-in-progress", dict(sent, state="succeeded"), {"kind": "query", "result": "found",
         "external_state": "accepted"}, NO_DEDUPE, t0, "succeeded", "EI08: a terminal state absorbs a later result")
    case("ei30-lease-lost", {"state": "sending"}, {"kind": "lease_lost"}, NO_DEDUPE, t0, "unknown",
         "EI29, EI30: the claimant gone while sending: unknown, queried, not resent")
    case("claim-past-deadline", dict(sent, state="retry_wait", resend_deadline=deadline(sent, DEDUPE_24H)),
         {"kind": "claim"}, DEDUPE_24H, "2026-11-06T09:30:00.000000Z", "unknown")
    case("ei40-past-deadline-before-send", dict(sent, resend_deadline=deadline(sent, DEDUPE_24H)),
         {"kind": "before_send"}, DEDUPE_24H, "2026-11-06T07:40:00.000000Z", "unknown",
         "EI40: within the deadline at the claim, past it before the send: not sent")
    acc = {"state": "accepted", "accepted_at": t0}
    case("ei31-no-query-manual", acc, {"kind": "finality_passed"}, {}, "2026-11-06T10:00:01.000000Z", "manual",
         "EI31: no query, past the manual limit")
    case("ei31-query", acc, {"kind": "finality_passed"}, NO_DEDUPE, "2026-11-06T10:00:01.000000Z", "accepted")
    case("manual-registered", {"state": "manual"}, {"kind": "registered", "result": "succeeded"}, NO_DEDUPE, t0,
         "succeeded")
    case("off-table", {"state": "prepared"}, {"kind": "send_result", "result": "succeeded"}, NO_DEDUPE, t0, "prepared")

    # the deadline's formula (P13.7)
    for cid, caps, cmd, want in [
        ("deadline-24h", DEDUPE_24H, {"first_reached_at": t0}, "2026-11-06T07:36:00.000000Z"),
        ("deadline-2h-margin-1h", dict(DEDUPE_24H, dedupe_window=7200), {"first_reached_at": t0}, "2026-11-05T11:00:00.000000Z"),
        ("deadline-none-without-reach", DEDUPE_24H, {}, None),
        ("deadline-none-without-dedupe", NO_DEDUPE, {"first_reached_at": t0}, None)]:
        got = deadline(cmd, caps)
        assert got == want, (cid, got)
        cases.append({"id": cid, "input": {"command": cmd, "capabilities": caps}, "expected": {"resend_deadline": got}})

    # the request's idempotency (P13.2): the parameters' digest tells a reused reference
    p1, p2 = {"amount": "100.00", "currency": "EUR"}, {"amount": "120.00", "currency": "EUR"}
    d1, d2 = digest("be.external.command_params", 1, p1), digest("be.external.command_params", 1, p2)
    cases.append({"id": "ei05-same-reference-other-amount", "description": "EI05",
                  "input": {"stored": d1, "incoming": p2}, "expected": {"digest": d2, "answer": "IDEMPOTENCY_KEY_REUSED"}})
    cases.append({"id": "same-reference-same-params", "input": {"stored": d1, "incoming": p1},
                  "expected": {"digest": d1, "answer": "existing"}})
    write("external-command", ["P13.2", "P13.3", "P13.4", "P13.5", "P13.6", "P13.7", "P13.8"],
          "对外命令：状态转移（按行序第一条命中）、查询“不存在”之后是否重发、重发截止时刻的公式、请求按参考号与参数摘要的幂等",
          cases, {"input": "command, event, capabilities, now | command, capabilities | stored, incoming",
                  "expected": "state, reason | resend_deadline | digest, answer"})


def reconcile(commands, external, issued, caps, T, now, failed_at=None):
    """P13.12: the step 7 matching, first matching row wins. commands: the local commands not final (sending_at: the
    start of a send attempt that has not ended); external: the external records by reference; issued: the issue
    records' references; failed_at: until when sends may have gone unrecorded (default now). Answers one conclusion
    per reference."""
    out = {}
    for c in commands:
        ref = c["reference"]
        if ref in external:
            s = external[ref]
            out[ref] = {"conclusion": "matched", "state": s if s in TERMINAL or s == "accepted" else "accepted"}
            continue
        if c["state"] == "manual":
            out[ref] = {"conclusion": "manual", "reason": "manual: only a person registers it"}
            continue
        first = c.get("first_reached_at") or c.get("sending_at") or T  # the earliest send that may have reached
        facts = dict(c, first_reached_at=first, unrecorded_until=failed_at or now)
        d = deadline(facts, caps)
        if d and t(now) <= t(d):
            out[ref] = {"conclusion": "deadline", "resend_deadline": d}
            continue
        action, why = not_found(dict(facts, resend_deadline=None), {k: v for k, v in caps.items() if k != "dedupe_window"}, now)
        out[ref] = {"conclusion": "unknown" if action == "resend" else "manual", "reason": why}
    local = {c["reference"] for c in commands} | set(external.get("_final_local", []))
    for ref in external:
        if ref not in local and not ref.startswith("_"):
            out[ref] = {"conclusion": "external_only"}
    for ref in issued:
        if ref not in local and ref not in external:
            out[ref] = {"conclusion": "possibly_executed"}
    return out


def reconcile_vectors():
    T, now = "2026-11-05T10:00:00.000000Z", "2026-11-05T14:00:00.000000Z"
    cmds = [
        {"reference": "p-matched", "state": "retry_wait", "first_reached_at": "2026-11-05T10:10:00.000000Z"},
        {"reference": "p-prepared-dedupe", "state": "prepared"},
        {"reference": "p-sending-dedupe", "state": "sending", "sending_at": "2026-11-05T09:00:00.000000Z"},
        {"reference": "p-sending-old", "state": "unknown", "sending_at": "2026-11-03T09:00:00.000000Z"},
        {"reference": "p-old", "state": "unknown", "first_reached_at": "2026-11-03T10:00:00.000000Z"},
        {"reference": "p-expired", "state": "unknown", "first_reached_at": "2026-11-05T11:00:00.000000Z",
         "last_reached_at": "2026-11-05T11:00:00.000000Z", "expires_at": "2026-11-05T12:00:00.000000Z"},
    ]
    external = {"p-matched": "succeeded", "p-external-only": "succeeded"}
    issued = ["p-matched", "p-issued-lost"]
    got = reconcile(cmds, external, issued, DEDUPE_24H, T, now)
    want = {"p-matched": "matched", "p-prepared-dedupe": "deadline", "p-sending-dedupe": "deadline",
            "p-sending-old": "manual", "p-old": "manual",
            "p-expired": "deadline", "p-external-only": "external_only", "p-issued-lost": "possibly_executed"}
    assert {k: v["conclusion"] for k, v in got.items()} == want, got
    no_dedupe = reconcile([{"reference": "p-x", "state": "prepared"}], {}, [], NO_DEDUPE, T, now)
    assert no_dedupe["p-x"]["conclusion"] == "manual"
    exp = [{"reference": "p-y", "state": "unknown", "first_reached_at": "2026-11-05T11:00:00.000000Z",
            "last_reached_at": "2026-11-05T11:00:00.000000Z", "expires_at": "2026-11-05T12:00:00.000000Z"}]
    expired = reconcile(exp, {}, [], NO_DEDUPE, T, now)
    assert expired["p-y"]["conclusion"] == "unknown", expired
    last_use = dict(DEDUPE_24H, window_from="last_use")
    more = [{"reference": "p-last-use", "state": "prepared"}, {"reference": "p-manual", "state": "manual"},
            {"reference": "p-manual-found", "state": "manual"}, {"reference": "p-pending", "state": "sending",
                                                                 "sending_at": "2026-11-05T09:30:00.000000Z"}]
    ext2 = {"p-manual-found": "failed", "p-pending": "processing"}
    others = reconcile(more, ext2, [], last_use, T, now)
    mp = dict(NO_DEDUPE, max_processing=3600)
    fails = [{"reference": "p-mp", "state": "retry_wait"}]
    after_failure = reconcile(fails, {}, [], mp, T, now, failed_at="2026-11-05T12:30:00.000000Z")
    within = reconcile(fails, {}, [], mp, T, now, failed_at="2026-11-05T13:30:00.000000Z")
    assert after_failure["p-mp"]["conclusion"] == "unknown" and within["p-mp"]["conclusion"] == "manual", (after_failure, within)
    assert {k: (v["conclusion"], v.get("state")) for k, v in others.items()} == {
        "p-last-use": ("deadline", None), "p-manual": ("manual", None), "p-manual-found": ("matched", "failed"),
        "p-pending": ("matched", "accepted")}, others
    cases = [{"id": "step-7", "input": {"T": T, "now": now, "commands": cmds, "external": external, "issued": issued,
                                        "capabilities": DEDUPE_24H}, "expected": got},
             {"id": "no-dedupe-prepared", "input": {"T": T, "now": now, "commands": [{"reference": "p-x", "state": "prepared"}],
                                                    "external": {}, "issued": [], "capabilities": NO_DEDUPE},
              "expected": no_dedupe},
             {"id": "no-dedupe-expired", "input": {"T": T, "now": now, "commands": exp, "external": {}, "issued": [],
                                                   "capabilities": NO_DEDUPE}, "expected": expired},
             {"id": "last-use-manual-not-final", "input": {"T": T, "now": now, "commands": more, "external": ext2,
                                                           "issued": [], "capabilities": last_use}, "expected": others},
             {"id": "longest-processing-after-the-failure", "input": {"T": T, "now": now, "commands": fails, "external": {},
              "issued": [], "capabilities": mp, "failed_at": "2026-11-05T12:30:00.000000Z"}, "expected": after_failure},
             {"id": "longest-processing-within", "input": {"T": T, "now": now, "commands": fails, "external": {},
              "issued": [], "capabilities": mp, "failed_at": "2026-11-05T13:30:00.000000Z"}, "expected": within}]
    write("external-reconcile", ["P13.12"],
          "整套恢复第 7 步的外部对账：对上而终结（外部未终结的取 accepted）、写重发截止（保留期从最近一次起算的也写）、unknown、manual（manual 不被降级）、外部有本地无、可能已对外执行待核实",
          cases, {"input": "T, now, commands, external, issued, capabilities, failed_at", "expected": "reference -> conclusion"})
