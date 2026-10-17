#!/usr/bin/env python3
"""Generate the vectors of chapters 02-04 and vectors/SHA256SUMS.

The scenarios are chosen by hand (edges, transitions); the expected values come from the small reference computations
below. The Go test (vectors_test.go) recomputes every expectation with an independent implementation, so a slip in
either one shows up. Run from the repository root: python3 scripts/gen-vectors.py
"""
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROTOCOL = "3.0.0-alpha.1"
VEC = ROOT / "vectors"


def write(topic, rules, description, cases, fields):
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), f"{topic}: duplicate ids"
    doc = {"topic": topic, "protocol": PROTOCOL, "rules": rules, "description": description,
           "fields": fields, "cases": cases}
    (VEC / f"{topic}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


# ---------------------------------------------------------------- errors (P3.9, catalog)
CODE_HTTP = {"OK": 200, "INVALID_ARGUMENT": 400, "FAILED_PRECONDITION": 400, "OUT_OF_RANGE": 400,
             "UNAUTHENTICATED": 401, "PERMISSION_DENIED": 403, "NOT_FOUND": 404, "ALREADY_EXISTS": 409,
             "ABORTED": 409, "RESOURCE_EXHAUSTED": 429, "CANCELLED": 499, "INTERNAL": 500, "UNKNOWN": 500,
             "DATA_LOSS": 500, "UNIMPLEMENTED": 501, "UNAVAILABLE": 503, "DEADLINE_EXCEEDED": 504}
LOG = {"INTERNAL": "error", "UNKNOWN": "error", "DATA_LOSS": "error", "UNAVAILABLE": "warn",
       "DEADLINE_EXCEEDED": "warn", "CANCELLED": "none"}
# reason, grpc code, http (None = by the code), retryable
REASONS = [
    ("REQUEST_INVALID", "INVALID_ARGUMENT", None, "no"), ("BODY_TOO_LARGE", "INVALID_ARGUMENT", 413, "no"),
    ("CURSOR_INVALID", "INVALID_ARGUMENT", None, "no"), ("BATCH_TOO_LARGE", "INVALID_ARGUMENT", None, "no"),
    ("TOKEN_INVALID", "UNAUTHENTICATED", None, "no"), ("TOKEN_STALE", "UNAUTHENTICATED", None, "after_refresh"),
    ("SERVICE_CREDENTIAL_INVALID", "UNAUTHENTICATED", None, "no"),
    ("PERMISSION_DENIED", "PERMISSION_DENIED", None, "no"), ("CONTAINMENT_NOT_PROVEN", "PERMISSION_DENIED", None, "no"),
    ("NOT_FOUND", "NOT_FOUND", None, "no"), ("QUERY_NOT_COMPLETABLE", "FAILED_PRECONDITION", 422, "no"),
    ("FIELD_NOT_QUERYABLE", "FAILED_PRECONDITION", 422, "no"), ("QUERY_PLAN_CHANGED", "ABORTED", None, "no"),
    ("CHANGE_KEY_CONFLICT", "ALREADY_EXISTS", None, "no"), ("CHANGE_REVISION_STALE", "ABORTED", None, "no"),
    ("LAST_ADMIN_PROTECTED", "FAILED_PRECONDITION", 409, "no"),
    ("IDEMPOTENCY_KEY_REUSED", "INVALID_ARGUMENT", 422, "no"), ("IDEMPOTENCY_IN_PROGRESS", "ABORTED", None, "yes"),
    ("LOCK_TIMEOUT", "ABORTED", None, "yes"), ("TX_CONFLICT", "ABORTED", None, "yes"),
    ("STATEMENT_TIMEOUT", "DEADLINE_EXCEEDED", None, "yes"), ("SERVICE_BUSY", "UNAVAILABLE", None, "yes"),
    ("OUTBOUND_LIMIT", "RESOURCE_EXHAUSTED", 503, "yes"), ("CIRCUIT_OPEN", "UNAVAILABLE", None, "yes"),
    ("DEPENDENCY_UNAVAILABLE", "UNAVAILABLE", None, "yes"),
    ("DEADLINE_BUDGET_EXHAUSTED", "DEADLINE_EXCEEDED", None, "no"),
    ("DEADLINE_EXCEEDED", "DEADLINE_EXCEEDED", None, "query_first"), ("REQUEST_CANCELLED", "CANCELLED", None, "none"),
    ("NOT_READY", "UNAVAILABLE", None, "yes"), ("AUTHORIZATION_UNPROVABLE", "UNAVAILABLE", None, "yes"),
    ("AUTHORIZATION_VIEW_EXPIRED", "UNAVAILABLE", None, "yes"), ("RECOVERY_IN_PROGRESS", "UNAVAILABLE", None, "yes"),
    ("MEMBER_SWITCH_IN_PROGRESS", "UNAVAILABLE", None, "yes"),
    ("CAPABILITY_UNSUPPORTED", "UNIMPLEMENTED", None, "no"), ("RESULT_UNKNOWN", "DEADLINE_EXCEEDED", None, "query_first"),
    ("INTERNAL", "INTERNAL", None, "no"),
]


def access_level(status):
    return "error" if status == 500 else "warn" if status in (503, 504) else "info"


def errors():
    cases = []
    for reason, code, http, retry in REASONS:
        h = http or CODE_HTTP[code]
        cases.append({"id": f"reason-{reason.lower()}", "kind": "reason", "reason": reason, "domain": "be",
                      "grpc_code": code, "http": h, "retryable": retry, "log_level": LOG.get(code, "info"),
                      "type": f"urn:be:be:{reason}"})
    for code, h in CODE_HTTP.items():
        if code == "OK":
            continue
        cases.append({"id": f"code-{code.lower()}", "kind": "code", "grpc_code": code, "http": h,
                      "log_level": LOG.get(code, "info")})
    for status in (200, 201, 202, 204, 400, 401, 403, 404, 409, 413, 422, 429, 499, 500, 501, 503, 504):
        cases.append({"id": f"access-{status}", "kind": "access_log", "http": status, "log_level": access_level(status)})
    write("errors", ["P3.1", "P3.2", "P3.7", "P3.9"],
          "平台原因目录与 gRPC 码、HTTP 状态、日志级别的对应。kind=reason：一个平台 reason；kind=code：没有指定 HTTP 的 reason 按 gRPC 码取 HTTP；kind=access_log：访问日志按 HTTP 状态定级别。retryable 取 no、yes、after_refresh（边缘换取新令牌后一次）、query_first（查询后再定）、none（不适用）；log_level 的 none 表示不按错误记。",
          cases, {"kind": "reason | code | access_log", "reason": "平台 reason", "domain": "be",
                  "grpc_code": "gRPC 码名", "http": "HTTP 状态", "retryable": "见说明", "log_level": "error | warn | info | none",
                  "type": "错误体的 type"})


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
    WINDOW, OPEN_MS, CLOSE_AFTER = 20, 30000, 3

    def __init__(self):
        self.state, self.results, self.opened_at, self.trial, self.trial_ok = "closed", [], None, None, 0

    def start(self, now, call):
        if self.state == "open":
            if now - self.opened_at >= self.OPEN_MS:
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
            else:
                self.trial_ok += 1
                if self.trial_ok >= self.CLOSE_AFTER:
                    self.state, self.results = "closed", []
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
        "open-rejects-before-cooldown": calls("c", 0, [f] * 20) + [{"at_ms": 29999, "kind": "start", "call": "x"}],
        "half-open-after-cooldown-one-trial": calls("c", 0, [f] * 20) + [
            {"at_ms": 30000, "kind": "start", "call": "t1"}, {"at_ms": 30001, "kind": "start", "call": "t2"}],
        "three-trial-successes-close": calls("c", 0, [f] * 20) + calls("t", 30000, [s, s, s]),
        "two-trial-successes-stay-half-open": calls("c", 0, [f] * 20) + calls("t", 30000, [s, s]),
        "trial-failure-reopens-and-restarts-timer": calls("c", 0, [f] * 20) + calls("t", 30000, [s, f]) + [
            {"at_ms": 59999, "kind": "start", "call": "y"}, {"at_ms": 60000, "kind": "start", "call": "z"}],
        "ignored-trial-frees-the-slot": calls("c", 0, [f] * 20) + [
            {"at_ms": 30000, "kind": "start", "call": "t1"}, {"at_ms": 30001, "kind": "end", "call": "t1", "outcome": ig},
            {"at_ms": 30002, "kind": "start", "call": "t2"}],
        "late-result-while-open-is-dropped": [{"at_ms": 0, "kind": "start", "call": "slow"}] + calls("c", 0, [f] * 20) + [
            {"at_ms": 100, "kind": "end", "call": "slow", "outcome": s}],
        "closed-again-starts-empty": calls("c", 0, [f] * 20) + calls("t", 30000, [s, s, s]) + calls("d", 30001, [f] * 19),
    }
    cases = [{"id": name, "steps": run(steps)} for name, steps in scen.items()]
    write("circuit-breaker", ["P4.11", "P4.12", "P4.13", "P4.14"],
          "熔断器的状态转换。steps 依次执行：kind=start 是一次要发出的调用（expect 为 sent 或 rejected），kind=end 是这次调用的结果（outcome 为 success、failure 或 ignored，ignored 表示不计入的结果，如业务错误）；expect_state 是这一步之后的状态。",
          cases, {"steps[].at_ms": "这一步的时刻（毫秒，单调时钟）", "steps[].kind": "start | end", "steps[].call": "调用的标识",
                  "steps[].outcome": "success | failure | ignored", "steps[].expect": "sent | rejected",
                  "steps[].expect_state": "closed | open | half_open"})


# ---------------------------------------------------------------- config parse (P2.4, P2.5)
DUR = re.compile(r"^(0|[1-9][0-9]*)(ms|s|m|h)$")
INT = re.compile(r"^-?(0|[1-9][0-9]*)$")


def parse(t, v, required, default, values=None):
    if v is None or v == "":
        if required:
            return {"error": "missing"}
        return {"value": default}
    if t == "string":
        return {"value": v}
    if t == "integer":
        return {"value": int(v)} if INT.match(v) and v != "-0" else {"error": "invalid"}
    if t == "boolean":
        return {"value": v == "true"} if v in ("true", "false") else {"error": "invalid"}
    if t == "duration":
        m = DUR.match(v)
        if not m:
            return {"error": "invalid"}
        mult = {"ms": 1, "s": 1000, "m": 60000, "h": 3600000}[m.group(2)]
        return {"value": int(m.group(1)) * mult}
    if t == "enum":
        return {"value": v} if v in values else {"error": "unknown_enum"}
    raise ValueError(t)


def config_parse_vectors():
    rows = [
        ("string-plain", "string", "abc", True, None, None), ("string-spaces-kept", "string", " a b ", True, None, None),
        ("required-unset", "string", None, True, None, None), ("required-empty", "string", "", True, None, None),
        ("optional-unset-default", "string", None, False, "x", None), ("optional-empty-default", "integer", "", False, 7, None),
        ("int-zero", "integer", "0", True, None, None), ("int-negative", "integer", "-42", True, None, None),
        ("int-plus", "integer", "+1", True, None, None), ("int-leading-zero", "integer", "007", True, None, None),
        ("int-space", "integer", " 1", True, None, None), ("int-minus-zero", "integer", "-0", True, None, None),
        ("int-invalid-not-default", "integer", "abc", False, 7, None),
        ("bool-true", "boolean", "true", True, None, None), ("bool-false", "boolean", "false", True, None, None),
        ("bool-upper", "boolean", "TRUE", True, None, None), ("bool-one", "boolean", "1", True, None, None),
        ("bool-yes", "boolean", "yes", True, None, None),
        ("dur-ms", "duration", "1500ms", True, None, None), ("dur-s", "duration", "3s", True, None, None),
        ("dur-m", "duration", "2m", True, None, None), ("dur-h", "duration", "1h", True, None, None),
        ("dur-zero", "duration", "0s", True, None, None), ("dur-fraction", "duration", "1.5s", True, None, None),
        ("dur-compound", "duration", "1m30s", True, None, None), ("dur-no-unit", "duration", "30", True, None, None),
        ("dur-us", "duration", "10us", True, None, None),
        ("enum-ok", "enum", "warn", True, None, ["debug", "info", "warn", "error"]),
        ("enum-case", "enum", "WARN", True, None, ["debug", "info", "warn", "error"]),
        ("enum-unset-default", "enum", None, False, "info", ["debug", "info", "warn", "error"]),
    ]
    cases = []
    for cid, t, v, req, d, vals in rows:
        c = {"id": cid, "type": t, "value": v, "required": req, "default": d}
        if vals:
            c["values"] = vals
        c["expect"] = parse(t, v, req, d, vals)
        cases.append(c)
    write("config-parse", ["P2.4", "P2.5"],
          "配置值的严格解析。value 为 null 表示未设置；expect.value 是解析结果（duration 以毫秒表示），expect.error 是错误类别（missing、invalid、unknown_enum）。不合法的值不回退到缺省值。",
          cases, {"type": "string | integer | boolean | duration | enum", "value": "原始字符串或 null", "required": "是否必填",
                  "default": "声明的缺省值", "values": "enum 的取值", "expect": "{value} 或 {error}"})


def sums():
    lines = []
    for p in sorted(VEC.glob("*.json")):
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (VEC / "SHA256SUMS").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    VEC.mkdir(exist_ok=True)
    errors()
    outbound_timeout()
    retry_decision_vectors()
    retry_budget_vectors()
    circuit_breaker_vectors()
    config_parse_vectors()
    sums()
    print("\n".join(sorted(p.name for p in VEC.iterdir())))
