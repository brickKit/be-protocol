#!/usr/bin/env python3
"""Generate the vectors of chapters 02-05 and vectors/SHA256SUMS.

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


# ---------------------------------------------------------------- events (P6.1, P6.4, P6.9, P6.13)
def fnv1a64(b):
    h = 0xcbf29ce484222325
    for x in b:
        h ^= x
        h = (h * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return h


def partition_vectors():
    ids = ["0190f3a1-7b2c-7def-8a01-23456789abcd", "0190F3A1-7B2C-7DEF-8A01-23456789ABCD",
           "00000000-0000-0000-0000-000000000000", "ffffffff-ffff-ffff-ffff-ffffffffffff",
           "0192a3b4-c5d6-7e8f-9a0b-1c2d3e4f5a6b", "019abcde-f012-7345-8678-9abcdef01234"]
    cases = []
    for rid in ids:
        canon = rid.lower()
        h = fnv1a64(canon.encode())
        for n in (1, 2, 4, 7, 16, 256):
            cases.append({"id": f"{canon[:8]}-{'upper' if rid != canon else 'lower'}-{n}", "record_id": rid,
                          "partitions": n, "hash": str(h), "expect": h % n})
    write("partition", ["P6.1"],
          "分区 = FNV-1a 64 位（记录身份转成小写后的 UTF-8 字节）对分区数取余。hash 是 64 位无符号的十进制字符串（避免 JSON 数字丢精度）；"
          "大写的身份与小写的落在同一分区。",
          cases, {"record_id": "记录身份", "partitions": "流声明的分区数", "hash": "FNV-1a 64 位，十进制字符串",
                  "expect": "分区"})


def envelope_vectors():
    import hashlib as _h
    base = {"event_id": "0190f3a1-7b2c-7def-8a01-23456789abcd", "source": "erp/inventory",
            "type": "erp.inventory.stock_moved.v1", "time": "2026-10-17T08:30:00.123Z",
            "record_id": "0190f3a1-0000-7000-8000-000000000001", "stream": "erp.inventory.stock", "partition": 3,
            "impl": "6f1c2d3e-4a5b-4c6d-8e7f-901234567890", "epoch": [1, 1], "seq": 42, "version": 7,
            "projection": "full", "hops": 0, "payload": '{"qty":"5.000","sku":"A-1"}'}
    variants = [
        ("full-state", {}),
        ("caused-by-another-event", {"causation": "0190f3a0-1111-7222-8333-444455556666", "hops": 3}),
        ("transaction-fact-with-legal-entity", {"legal_entity": "LE1", "projection": "partial"}),
        ("watermark-source-subjects", {"subjects": ["acc:01", "org:7"], "type": "mdm.org.unit_changed.v1",
                                        "source": "mdm/org", "stream": "mdm.org.units"}),
        ("delete", {"projection": "delete", "payload": "{}", "version": 8}),
        ("new-epoch", {"epoch": [2, 3], "seq": 1}),
        ("claim-check", {"claim": True, "payload": '{"claim":{"uri":"s3://b/k","size":70000,"sha256":"' + "0" * 64 + '"}}'}),
        ("with-trace", {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}),
    ]
    cases = []
    for name, v in variants:
        e = dict(base, **v)
        payload = e["payload"].encode()
        digest = _h.sha256(e["event_id"].encode() + b"\x00" + payload).hexdigest()
        h = {"ce-specversion": "1.0", "ce-id": e["event_id"], "ce-source": "urn:be:" + e["source"], "ce-type": e["type"],
             "ce-time": e["time"], "ce-subject": e["record_id"], "ce-datacontenttype": "application/json",
             "ce-bestream": e["stream"], "ce-bepartition": str(e["partition"]), "ce-beimpl": e["impl"],
             "ce-beepoch": f"{e['epoch'][0]}.{e['epoch'][1]}", "ce-beseq": str(e["seq"]),
             "ce-beversion": str(e["version"]), "ce-beprojection": e["projection"], "ce-bedigest": digest,
             "ce-behops": str(e["hops"])}
        if "causation" in e:
            h["ce-becausation"] = e["causation"]
        if "legal_entity" in e:
            h["ce-belegalentity"] = e["legal_entity"]
        if "subjects" in e:
            h["ce-besubjects"] = json.dumps(e["subjects"], separators=(",", ":"))
        if e.get("claim"):
            h["ce-beclaim"] = "true"
        if "traceparent" in e:
            h["ce-traceparent"] = e["traceparent"]
        cases.append({"id": name, "event": e, "expect": {"headers": h, "digest": digest,
                                                         "subject": f"be.{e['stream']}.{e['partition']}.{e['type']}"}})
    write("envelope", ["P6.4", "P6.9", "P6.13", "P6.17"],
          "一条发件行发布成什么：消息头（CloudEvents 二进制模式，ce- 前缀）、行摘要（SHA-256（事件身份、0 字节、载荷字节），小写十六进制）"
          "与主题。event.payload 是载荷的确切字节（UTF-8）；epoch 是（代次，时间线）。besubjects 是紧凑 JSON（无空白）。"
          "消息头逐个相等，不多不少。",
          cases, {"event": "发件行的字段", "expect.headers": "消息头", "expect.digest": "行摘要", "expect.subject": "主题"})


# ---------------------------------------------------------------- database (P5.7, P5.8, P5.13)
def db_errors_vectors():
    # sqlstate, reason, retried inside the transaction entry
    rows = [
        ("40001", "TX_CONFLICT", True, "serialization failure; retried, then TX_CONFLICT"),
        ("40P01", "TX_CONFLICT", True, "deadlock; retried, then TX_CONFLICT"),
        ("55P03", "LOCK_TIMEOUT", False, "lock_timeout"),
        ("57014", "STATEMENT_TIMEOUT", False, "statement_timeout (query canceled)"),
        ("53300", "DEPENDENCY_UNAVAILABLE", False, "too many connections"),
        ("57P01", "DEPENDENCY_UNAVAILABLE", False, "admin shutdown"),
        ("57P02", "DEPENDENCY_UNAVAILABLE", False, "crash shutdown"),
        ("57P03", "DEPENDENCY_UNAVAILABLE", False, "cannot connect now"),
        ("23505", "INTERNAL", False, "unique violation the module did not handle"),
        ("42P01", "INTERNAL", False, "undefined table"),
        ("connect", "DEPENDENCY_UNAVAILABLE", False, "no connection could be made (not an SQLSTATE)"),
    ]
    cases = [{"id": f"db-{state}", "sqlstate": state, "reason": reason, "retried": retried, "note": note}
             for state, reason, retried, note in rows]
    write("db-errors", ["P5.7", "P5.8"],
          "到达事务入口的数据库错误：哪些重试（重做整个事务，最多 3 次尝试），最终答哪个 reason。sqlstate 为 connect 表示还没有 "
          "SQLSTATE 的连接失败。DEPENDENCY_UNAVAILABLE 带 metadata dependency=db。模块自己返回的错误原样传出。",
          cases, {"sqlstate": "SQLSTATE，或 connect", "reason": "domain 为 be 的 reason",
                  "retried": "是否在事务入口内重试", "note": "说明"})


LINT_RULES = {
    "NAME": "文件名不是 <版本>_<小写下划线标题>.up.sql",
    "DOWN": "回退迁移（生产只向前）",
    "DUP_VERSION": "两个文件版本相同",
    "SET": "语句以 SET 或 RESET 开头",
    "TX_CONTROL": "语句以 BEGIN、START TRANSACTION、COMMIT、END、ROLLBACK、SAVEPOINT 或 RELEASE 开头",
    "GRANT": "语句以 GRANT、REVOKE 或 REASSIGN 开头",
    "ROLE_SCHEMA": "CREATE、ALTER 或 DROP 一个 ROLE、USER、GROUP 或 SCHEMA",
    "DEFAULT_PRIVILEGES": "ALTER DEFAULT PRIVILEGES",
    "DROP_OWNED": "DROP OWNED",
    "OWNER": "语句中任何位置的 OWNER TO",
    "CONCURRENTLY": "语句中任何位置的 CONCURRENTLY（不能在文件的事务中执行）",
    "SCHEMA_NAME": "用组件自己的 schema 名限定名字（<schema>. 或带双引号的 \"<schema>\".）",
}


def migration_lint_vectors():
    cases = [
        {"id": "plain-structure", "schema": "sales", "files": {
            "0001_orders.up.sql": "CREATE TABLE orders (id uuid PRIMARY KEY, status text NOT NULL);\n"
                                  "ALTER TABLE orders ALTER COLUMN status SET DEFAULT 'draft';\n"
                                  "CREATE INDEX orders_status ON orders (status);"}, "refused": []},
        {"id": "comments-and-literals-ignored", "schema": "sales", "files": {
            "0001_a.up.sql": "-- SET search_path = x;\n/* GRANT ALL */ CREATE TABLE a (note text DEFAULT 'COMMIT; SET x');\n"
                             "ALTER TABLE a ADD COLUMN \"sales.x\" int;"}, "refused": []},
        {"id": "function-body-is-one-statement", "schema": "sales", "files": {
            "0001_f.up.sql": "CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS $body$\nBEGIN\n  SET LOCAL lock_timeout = '1s';\n"
                             "  PERFORM 1;\nEND $body$;"}, "refused": []},
        {"id": "session-and-transaction-control", "schema": "sales", "files": {
            "0001_a.up.sql": "SET search_path = public;\nBEGIN;\nCREATE TABLE a (id int);\nCOMMIT;\nreset all;"},
         "refused": [{"file": "0001_a.up.sql", "rule": "SET"}, {"file": "0001_a.up.sql", "rule": "TX_CONTROL"},
                     {"file": "0001_a.up.sql", "rule": "TX_CONTROL"}, {"file": "0001_a.up.sql", "rule": "SET"}]},
        {"id": "provisioning-statements", "schema": "sales", "files": {
            "0001_a.up.sql": "GRANT SELECT ON a TO x;\ncreate role r;\nDROP SCHEMA s;\n"
                             "ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO x;\nDROP OWNED BY x;\n"
                             "ALTER TABLE a OWNER TO y;"},
         "refused": [{"file": "0001_a.up.sql", "rule": "GRANT"}, {"file": "0001_a.up.sql", "rule": "ROLE_SCHEMA"},
                     {"file": "0001_a.up.sql", "rule": "ROLE_SCHEMA"},
                     {"file": "0001_a.up.sql", "rule": "DEFAULT_PRIVILEGES"},
                     {"file": "0001_a.up.sql", "rule": "DROP_OWNED"}, {"file": "0001_a.up.sql", "rule": "OWNER"}]},
        {"id": "concurrently-and-own-schema", "schema": "sales", "files": {
            "0001_a.up.sql": "CREATE INDEX CONCURRENTLY i ON a (id);\nCREATE TABLE sales.b (id int);\n"
                             "CREATE TABLE \"sales\".c (id int);\nCREATE TABLE wholesales.d (id int);"},
         "refused": [{"file": "0001_a.up.sql", "rule": "CONCURRENTLY"}, {"file": "0001_a.up.sql", "rule": "SCHEMA_NAME"},
                     {"file": "0001_a.up.sql", "rule": "SCHEMA_NAME"}]},
        {"id": "file-names", "schema": "sales", "files": {
            "0001_a.down.sql": "DROP TABLE a;", "2_Bad-Name.up.sql": "SELECT 1;", "0003_x.up.sql": "SELECT 1;",
            "3_y.up.sql": "SELECT 1;", "README.md": "not a migration"},
         "refused": [{"file": "0001_a.down.sql", "rule": "DOWN"}, {"file": "2_Bad-Name.up.sql", "rule": "NAME"},
                     {"file": "3_y.up.sql", "rule": "DUP_VERSION"}]},
    ]
    for c in cases:
        for r in c["refused"]:
            assert r["rule"] in LINT_RULES, r
    write("migration-lint", ["P5.13"],
          "迁移文件与迁移入口检查的拒绝项。语句按顶层分号切分；注释、字符串字面量与美元引号包起来的正文不单独算语句；"
          "含点号的双引号标识符是一个名字。文件按名字排序检查，语句按文件中的顺序，同一语句内按下面规则列出的顺序。"
          "不以 .sql 结尾的文件忽略。规则：" + "；".join(f"{k}: {v}" for k, v in LINT_RULES.items()) + "。",
          cases, {"schema": "组件的 schema", "files": "文件名到内容", "refused": "按顺序期望的拒绝项：文件与规则"})


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
    call_outcomes_vectors()
    partition_vectors()
    envelope_vectors()
    config_parse_vectors()
    db_errors_vectors()
    migration_lint_vectors()
    sums()
    print("\n".join(sorted(p.name for p in VEC.iterdir())))
