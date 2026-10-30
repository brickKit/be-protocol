"""Chapter 04: outbound calls (P4.4-P4.19)."""
from ch03_errors import REASONS

from common import write


# ---------------------------------------------------------------- outbound timeout (P4.4)
def outbound(remaining):
    if remaining is None or remaining < 50:
        return {"send": False, "reason": "DEADLINE_BUDGET_EXHAUSTED"}
    return {"send": True, "timeout_ms": min(3000, remaining - 50)}


def outbound_timeout():
    cases = []
    for r in (None, 0, 1, 49, 50, 51, 100, 2999, 3049, 3050, 3051, 10000, 15000):
        cases.append({"id": f"remaining-{'none' if r is None else r}", "remaining_ms": r, "expect": outbound(r)})
    write("outbound-timeout", ["P4.4"],
          "一次出站尝试的时限：min(3000, 剩余 − 50) 毫秒；剩余不足 50 毫秒或没有剩余（null）时不发出。",
          cases, {"remaining_ms": "调用方手里剩余的毫秒数，null 表示已没有截止时间余量", "expect.send": "是否发出",
                  "expect.timeout_ms": "发出时这次尝试的时限", "expect.reason": "不发出时的 reason"})


# ---------------------------------------------------------------- retry decision (P4.6, P4.7)
def retry_decision(c):
    if not c["idempotent"]:
        return "stop"
    if c["outcome"] not in ("UNAVAILABLE", "CONNECT_FAILED_BEFORE_SEND"):
        return "stop"
    if c["attempts_made"] >= 3:
        return "stop"
    if not c["budget_allows"]:
        return "stop"
    after = c["remaining_ms_after_backoff"]
    if after is None or after < 50:
        return "stop"
    return "retry"


def retry_decision_vectors():
    base = {"idempotent": True, "outcome": "UNAVAILABLE", "attempts_made": 1, "budget_allows": True,
            "remaining_ms_after_backoff": 5000}
    variants = [
        ("unavailable-first-failure", {}),
        ("connect-failed-before-send", {"outcome": "CONNECT_FAILED_BEFORE_SEND"}),
        ("not-idempotent", {"idempotent": False}),
        ("deadline-exceeded", {"outcome": "DEADLINE_EXCEEDED"}),
        ("resource-exhausted", {"outcome": "RESOURCE_EXHAUSTED"}),
        ("business-error", {"outcome": "FAILED_PRECONDITION"}),
        ("internal", {"outcome": "INTERNAL"}),
        ("second-failure", {"attempts_made": 2}),
        ("third-failure-is-last", {"attempts_made": 3}),
        ("budget-exhausted", {"budget_allows": False}),
        ("no-time-after-backoff", {"remaining_ms_after_backoff": 49}),
        ("just-enough-time", {"remaining_ms_after_backoff": 50}),
        ("deadline-gone", {"remaining_ms_after_backoff": None}),
    ]
    cases = []
    for name, v in variants:
        c = dict(base, **v)
        c["id"] = name
        c["expect"] = retry_decision(c)
        cases.append(c)
    for n in range(1, 7):
        cases.append({"id": f"backoff-cap-after-{n}", "kind": "backoff", "failed_attempts": n,
                      "max_backoff_ms": min(1000, 100 * 2 ** (n - 1))})
    write("retry-decision", ["P4.6", "P4.7"],
          "一次尝试失败后是否再试。没有 kind 的项：给出方法是否幂等、这次的结果、已做的尝试次数（含刚失败的这次）、预算是否允许、退避之后的剩余毫秒，期望 retry 或 stop。kind=backoff：失败 n 次后退避的上限（实际退避在 [0, 上限] 内随机）。",
          cases, {"idempotent": "契约是否声明无副作用或幂等", "outcome": "这次尝试的结果（gRPC 码名，或 CONNECT_FAILED_BEFORE_SEND）",
                  "attempts_made": "已做的尝试次数", "budget_allows": "重试预算是否允许（P4.8）",
                  "remaining_ms_after_backoff": "退避之后的剩余毫秒，null 为没有", "expect": "retry | stop",
                  "failed_attempts": "已失败的次数", "max_backoff_ms": "退避上限"})


# ---------------------------------------------------------------- retry budget (P4.8), thousandths
class Budget:
    MAX, SUCCESS, FAILURE, THRESHOLD = 10000, 100, 1000, 5000

    def __init__(self):
        self.tokens = self.MAX

    def record(self, outcome):
        if outcome == "success":
            self.tokens = min(self.MAX, self.tokens + self.SUCCESS)
        elif outcome == "unavailable":
            self.tokens = max(0, self.tokens - self.FAILURE)

    def allows_retry(self):
        return self.tokens > self.THRESHOLD


def retry_budget_vectors():
    seqs = {
        "fresh-bucket-allows": [],
        "five-failures-reach-threshold": ["unavailable"] * 5,
        "four-failures-still-allow": ["unavailable"] * 4,
        "six-failures-then-ten-successes": ["unavailable"] * 6 + ["success"] * 10,
        "six-failures-then-eleven-successes": ["unavailable"] * 6 + ["success"] * 11,
        "other-outcomes-change-nothing": ["unavailable"] * 5 + ["other"] * 20,
        "floor-at-zero": ["unavailable"] * 15,
        "recover-from-zero": ["unavailable"] * 15 + ["success"] * 51,
        "cap-at-max": ["success"] * 30,
        "mixed": ["unavailable", "success", "unavailable", "unavailable", "success", "other", "unavailable",
                  "unavailable", "unavailable", "success", "success"],
    }
    cases = []
    for name, events in seqs.items():
        b = Budget()
        tokens, allowed = [], []
        for e in events:
            b.record(e)
            tokens.append(b.tokens)
            allowed.append(b.allows_retry())
        cases.append({"id": name, "events": events, "expect_tokens": tokens, "expect_retry_allowed": allowed,
                      "expect_final_retry_allowed": b.allows_retry()})
    write("retry-budget", ["P4.8"],
          "重试预算的令牌桶，以千分之一计：初始 10000，success 加 100（上限 10000），unavailable 减 1000（下限 0），other 不变；令牌严格大于 5000 时允许重试。expect_tokens 与 expect_retry_allowed 给出每个事件之后的值。",
          cases, {"events": "依次发生的尝试结果：success | unavailable | other", "expect_tokens": "每个事件之后的令牌数",
                  "expect_retry_allowed": "每个事件之后是否允许重试", "expect_final_retry_allowed": "全部事件之后"})


# ---------------------------------------------------------------- circuit breaker (P4.11-P4.14)
class Breaker:
    WINDOW, OPEN_FIRST_MS, OPEN_MAX_MS, CLOSE_AFTER = 20, 5000, 30000, 3

    def __init__(self):
        self.state, self.results, self.opened_at, self.trial, self.trial_ok = "closed", [], None, None, 0
        self.open_ms = self.OPEN_FIRST_MS  # the open period: doubles on a failed trial, resets on closing (P4.13)

    def start(self, now, call):
        if self.state == "open":
            if now - self.opened_at >= self.open_ms:
                self.state, self.trial, self.trial_ok = "half_open", None, 0
            else:
                return "rejected"
        if self.state == "half_open":
            if self.trial is not None:
                return "rejected"
            self.trial = call
            return "sent"
        return "sent"

    def end(self, now, call, outcome):
        if outcome == "ignored":
            if self.state == "half_open" and self.trial == call:
                self.trial = None
            return
        if self.state == "half_open":
            if self.trial != call:
                return  # a call sent while closed that finishes late: not a trial
            self.trial = None
            if outcome == "failure":
                self.state, self.opened_at, self.trial_ok = "open", now, 0
                self.open_ms = min(self.open_ms * 2, self.OPEN_MAX_MS)
            else:
                self.trial_ok += 1
                if self.trial_ok >= self.CLOSE_AFTER:
                    self.state, self.results, self.open_ms = "closed", [], self.OPEN_FIRST_MS
            return
        if self.state == "open":
            return  # late result of a call sent before opening
        self.results.append(outcome)
        self.results = self.results[-self.WINDOW:]
        if len(self.results) == self.WINDOW and self.results.count("failure") * 2 > self.WINDOW:
            self.state, self.opened_at, self.results = "open", now, []


def run(steps):
    b = Breaker()
    out = []
    for s in steps:
        s = dict(s)
        if s["kind"] == "start":
            s["expect"] = b.start(s["at_ms"], s["call"])
        else:
            b.end(s["at_ms"], s["call"], s["outcome"])
        s["expect_state"] = b.state
        out.append(s)
    return out


def calls(prefix, at, outcomes):
    steps = []
    for i, o in enumerate(outcomes):
        cid = f"{prefix}{i}"
        steps.append({"at_ms": at, "kind": "start", "call": cid})
        steps.append({"at_ms": at, "kind": "end", "call": cid, "outcome": o})
    return steps


def circuit_breaker_vectors():
    f, s, ig = "failure", "success", "ignored"
    scen = {
        "ten-of-twenty-stays-closed": calls("c", 0, [f, s] * 10),
        "eleven-of-twenty-opens": calls("c", 0, [f] * 11 + [s] * 9),
        "nineteen-failures-not-yet-full": calls("c", 0, [f] * 19),
        "ignored-results-do-not-count": calls("c", 0, [f] * 19 + [ig] * 5),
        "sliding-window": calls("c", 0, [s] * 10 + [f] * 10 + [f]),
        "open-rejects-before-cooldown": calls("c", 0, [f] * 20) + [{"at_ms": 4999, "kind": "start", "call": "x"}],
        "half-open-after-cooldown-one-trial": calls("c", 0, [f] * 20) + [
            {"at_ms": 5000, "kind": "start", "call": "t1"}, {"at_ms": 5001, "kind": "start", "call": "t2"}],
        "three-trial-successes-close": calls("c", 0, [f] * 20) + calls("t", 5000, [s, s, s]),
        "two-trial-successes-stay-half-open": calls("c", 0, [f] * 20) + calls("t", 5000, [s, s]),
        # a failed trial reopens for twice the period: 10 s after the trial, not 5
        "trial-failure-reopens-and-restarts-timer": calls("c", 0, [f] * 20) + calls("t", 5000, [s, f]) + [
            {"at_ms": 14999, "kind": "start", "call": "y"}, {"at_ms": 15000, "kind": "start", "call": "z"}],
        # each failed trial doubles the period up to 30 s: 5, 10, 20, then 30 and 30
        "failed-trials-double-up-to-thirty-seconds": calls("c", 0, [f] * 20) + calls("a", 5000, [f]) + [
            {"at_ms": 14999, "kind": "start", "call": "a1"}] + calls("b", 15000, [f]) + [
            {"at_ms": 34999, "kind": "start", "call": "b1"}] + calls("e", 35000, [f]) + [
            {"at_ms": 64999, "kind": "start", "call": "e1"}] + calls("g", 65000, [f]) + [
            {"at_ms": 94999, "kind": "start", "call": "g1"}] + calls("h", 95000, [s, s, s]),
        # closing resets the period: the next opening is 5 s again, though the last one was 10 s
        "closing-resets-the-open-period": calls("c", 0, [f] * 20) + calls("a", 5000, [f]) + calls("t", 15000, [s, s, s]) +
            calls("d", 15001, [f] * 20) + [{"at_ms": 20000, "kind": "start", "call": "x"}, {"at_ms": 20001, "kind": "start", "call": "y"}],
        "ignored-trial-frees-the-slot": calls("c", 0, [f] * 20) + [
            {"at_ms": 5000, "kind": "start", "call": "t1"}, {"at_ms": 5001, "kind": "end", "call": "t1", "outcome": ig},
            {"at_ms": 5002, "kind": "start", "call": "t2"}],
        "late-result-while-open-is-dropped": [{"at_ms": 0, "kind": "start", "call": "slow"}] + calls("c", 0, [f] * 20) + [
            {"at_ms": 100, "kind": "end", "call": "slow", "outcome": s}],
        "closed-again-starts-empty": calls("c", 0, [f] * 20) + calls("t", 5000, [s, s, s]) + calls("d", 5001, [f] * 19),
    }
    cases = [{"id": name, "steps": run(steps)} for name, steps in scen.items()]
    write("circuit-breaker", ["P4.11", "P4.12", "P4.13", "P4.14"],
          "熔断器的状态转换。steps 依次执行：kind=start 是一次要发出的调用（expect 为 sent 或 rejected），kind=end 是这次调用的结果（outcome 为 success、failure 或 ignored，ignored 表示不计入的结果，如业务错误）；expect_state 是这一步之后的状态。",
          cases, {"steps[].at_ms": "这一步的时刻（毫秒，单调时钟）", "steps[].kind": "start | end", "steps[].call": "调用的标识",
                  "steps[].outcome": "success | failure | ignored", "steps[].expect": "sent | rejected",
                  "steps[].expect_state": "closed | open | half_open"})


# ---------------------------------------------------------------- call outcomes (P4.6, P4.11, P4.18, P4.19)
RELAYED = {("be", "DEPENDENCY_UNAVAILABLE"), ("be", "CIRCUIT_OPEN"), ("be", "DEADLINE_BUDGET_EXHAUSTED"),
           ("be", "RESULT_UNKNOWN")}
REASON_CODE = {r: code for r, code, _, _ in REASONS}


def code_of(c):
    if c["surface"] == "grpc":
        return c["code"]
    p = c.get("problem")
    if p and p["domain"] == "be":
        return REASON_CODE[p["reason"]]
    return {200: "OK", 502: "UNAVAILABLE", 503: "UNAVAILABLE", 504: "DEADLINE_EXCEEDED"}.get(c["status"], "OTHER")


def classify(c):
    if c.get("caller_cancelled"):
        return "cancelled"
    if c.get("connect_failed"):
        return "connect_failed"
    code = code_of(c)
    info = c.get("problem") if c["surface"] == "http" else c.get("info")
    if code == "OK":
        return "success"
    if info and (info["domain"], info["reason"]) in RELAYED:
        return "relayed"
    if code == "UNAVAILABLE":
        return "unavailable"
    if code == "DEADLINE_EXCEEDED":
        return "deadline"
    return "other"


def expect(c):
    k = classify(c)
    breaker = {"success": "success", "unavailable": "failure", "connect_failed": "failure",
               "deadline": "failure"}.get(k, "ignored")
    budget = {"success": "success", "unavailable": "unavailable", "connect_failed": "unavailable"}.get(k, "other")
    retry = {"unavailable": "UNAVAILABLE", "connect_failed": "CONNECT_FAILED_BEFORE_SEND"}.get(k, "NONE")
    if k == "success":
        upward = None
    elif k in ("unavailable", "connect_failed"):
        upward = {"domain": "be", "reason": "DEPENDENCY_UNAVAILABLE", "metadata": {"dependency": c["dependency"]}}
    elif k == "deadline":
        upward = {"domain": "be", "reason": "DEADLINE_EXCEEDED" if c["idempotent"] else "RESULT_UNKNOWN",
                  "metadata": {"dependency": c["dependency"]}}
    elif k == "cancelled":
        upward = {"domain": "be", "reason": "REQUEST_CANCELLED"}
    else:
        upward = "unchanged"
    return {"class": k, "breaker": breaker, "budget": budget, "retry_outcome": retry, "upward": upward}


def call_outcomes_vectors():
    dep = "erp/inventory"
    g = lambda code, info=None, **kw: dict({"surface": "grpc", "code": code, "info": info}, **kw)
    h = lambda status, problem=None, **kw: dict({"surface": "http", "status": status, "problem": problem}, **kw)
    be = lambda reason: {"domain": "be", "reason": reason}
    scen = [
        ("grpc-ok", g("OK")),
        ("grpc-unavailable-transport", g("UNAVAILABLE")),
        ("grpc-service-busy", g("UNAVAILABLE", be("SERVICE_BUSY"))),
        ("grpc-not-ready", g("UNAVAILABLE", be("NOT_READY"))),
        ("grpc-relayed-dependency-unavailable", g("UNAVAILABLE", be("DEPENDENCY_UNAVAILABLE"))),
        ("grpc-relayed-circuit-open", g("UNAVAILABLE", be("CIRCUIT_OPEN"))),
        ("grpc-connect-failed", g("UNAVAILABLE", connect_failed=True)),
        ("grpc-attempt-timeout-idempotent", g("DEADLINE_EXCEEDED")),
        ("grpc-attempt-timeout-command", g("DEADLINE_EXCEEDED", idempotent=False)),
        ("grpc-relayed-budget-exhausted", g("DEADLINE_EXCEEDED", be("DEADLINE_BUDGET_EXHAUSTED"))),
        ("grpc-relayed-result-unknown", g("DEADLINE_EXCEEDED", be("RESULT_UNKNOWN"), idempotent=False)),
        ("grpc-not-found", g("NOT_FOUND", be("NOT_FOUND"))),
        ("grpc-component-reason", g("FAILED_PRECONDITION", {"domain": dep, "reason": "STOCK_SHORT"})),
        ("grpc-outbound-limit", g("RESOURCE_EXHAUSTED", be("OUTBOUND_LIMIT"))),
        ("grpc-internal", g("INTERNAL", be("INTERNAL"))),
        ("grpc-caller-cancelled", g("CANCELLED", caller_cancelled=True)),
        ("http-ok", h(200)),
        ("http-service-busy", h(503, be("SERVICE_BUSY"))),
        ("http-outbound-limit-is-not-unavailable", h(503, be("OUTBOUND_LIMIT"))),
        ("http-relayed-dependency-unavailable", h(503, be("DEPENDENCY_UNAVAILABLE"))),
        ("http-503-without-problem", h(503)),
        ("http-502-without-problem", h(502)),
        ("http-504-without-problem", h(504)),
        ("http-component-conflict", h(409, {"domain": "erp/sales", "reason": "ORDER_LOCKED"})),
        ("http-component-unavailable", h(503, {"domain": dep, "reason": "MAINTENANCE"})),
        ("http-connect-failed", h(None, connect_failed=True)),
    ]
    cases = []
    for name, c in scen:
        c = dict({"idempotent": True, "dependency": dep}, **c)
        c["id"] = name
        c["expect"] = expect(c)
        cases.append(c)
    write("call-outcomes", ["P4.6", "P4.8", "P4.11", "P4.18", "P4.19"],
          "一次尝试的结果怎样计入。surface=grpc：code 为 gRPC 码，info 为 ErrorInfo 的 domain 与 reason（没有时为 null）；"
          "surface=http：status 为 HTTP 状态，problem 为 problem+json 正文的 domain 与 reason（正文不是 problem+json 时为 null）。"
          "http 回答的码：平台 reason 取目录中的码，其余按状态（502、503 为 UNAVAILABLE，504 为 DEADLINE_EXCEEDED）。"
          "connect_failed：请求发出之前连接失败；caller_cancelled：调用方自己的上下文已结束。"
          "expect.class：success、unavailable、connect_failed、deadline、relayed（依赖转述的更下游的故障）、other、cancelled；"
          "breaker 与 budget：熔断器与重试预算记下什么；retry_outcome：交给重试决定（向量 retry-decision）的结果，NONE 表示从不重试；"
          "upward：这是最后一次尝试时调用方向上答什么（unchanged 表示依赖的错误原样）。",
          cases, {"surface": "grpc | http", "code": "gRPC 码名", "info": "ErrorInfo 的 domain 与 reason，或 null",
                  "status": "HTTP 状态，什么都没收到时为 null", "problem": "problem 正文的 domain 与 reason",
                  "idempotent": "方法是否声明为幂等", "dependency": "依赖的组件 ID",
                  "connect_failed": "发出之前失败", "caller_cancelled": "调用方已取消",
                  "expect": "class、breaker、budget、retry_outcome、upward"})
