#!/usr/bin/env python3
"""Generate vectors/errors/*.json (protocol P4, P10.4; foundations 10, 15, 23).

gRPC code <-> HTTP status, restoring a dependency's REST error, SQLSTATE
classification, the log level of an error, the problem+json body, the
Retry-After header and reason names. xcheck_errors.go recomputes every case
from tables typed in again, independently.
"""

import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_lib"))
from vecfile import CaseList, area_dir, write_file  # noqa: E402

GEN = "errors/gen/gen_errors.py"
OUT = area_dir(__file__)

CODES = ["OK", "CANCELLED", "UNKNOWN", "INVALID_ARGUMENT", "DEADLINE_EXCEEDED", "NOT_FOUND", "ALREADY_EXISTS",
         "PERMISSION_DENIED", "RESOURCE_EXHAUSTED", "FAILED_PRECONDITION", "ABORTED", "OUT_OF_RANGE",
         "UNIMPLEMENTED", "INTERNAL", "UNAVAILABLE", "DATA_LOSS", "UNAUTHENTICATED"]
HTTP = {"OK": 200, "CANCELLED": 499, "UNKNOWN": 500, "INVALID_ARGUMENT": 400, "DEADLINE_EXCEEDED": 504,
        "NOT_FOUND": 404, "ALREADY_EXISTS": 409, "PERMISSION_DENIED": 403, "RESOURCE_EXHAUSTED": 429,
        "FAILED_PRECONDITION": 400, "ABORTED": 409, "OUT_OF_RANGE": 400, "UNIMPLEMENTED": 501,
        "INTERNAL": 500, "UNAVAILABLE": 503, "DATA_LOSS": 500, "UNAUTHENTICATED": 401}
# reverse mapping, used only when a dependency answered without a problem+json body
FROM_HTTP = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED", 404: "NOT_FOUND",
             409: "ABORTED", 413: "INVALID_ARGUMENT", 429: "RESOURCE_EXHAUSTED", 499: "CANCELLED",
             501: "UNIMPLEMENTED", 502: "UNAVAILABLE", 503: "UNAVAILABLE", 504: "DEADLINE_EXCEEDED"}
HIDDEN = {"INTERNAL", "UNKNOWN", "DATA_LOSS"}
# platform reasons (domain be): schemas/errors-be.yaml (scripts/validate.py checks this table against it)
BE_REASONS = {
    "INTERNAL": "INTERNAL", "TOKEN_STALE": "UNAUTHENTICATED", "MISSING_PERMISSION": "PERMISSION_DENIED",
    "NOT_FOUND": "NOT_FOUND", "AUTHZ_NOT_READY": "UNAVAILABLE", "NOT_READY": "UNAVAILABLE",
    "TOKEN_INVALID": "UNAUTHENTICATED", "UNSUPPORTED_DELEGATION": "UNAUTHENTICATED",
    "MISSING_CALLER": "UNAUTHENTICATED", "OUT_OF_SCOPE": "PERMISSION_DENIED", "FIELD_FORBIDDEN": "PERMISSION_DENIED",
    "SORT_FORBIDDEN": "INVALID_ARGUMENT", "SHARE_NOT_ALLOWED": "PERMISSION_DENIED",
    "CAPABILITY_UNAVAILABLE": "UNIMPLEMENTED", "IDEMPOTENCY_MISMATCH": "INVALID_ARGUMENT",
    "IDEMPOTENCY_IN_PROGRESS": "ABORTED", "CURSOR_INVALID": "INVALID_ARGUMENT", "BATCH_TOO_LARGE": "INVALID_ARGUMENT",
    "LOCK_TIMEOUT": "ABORTED", "STATEMENT_TIMEOUT": "DEADLINE_EXCEEDED", "TX_CONFLICT": "ABORTED",
    "DB_POOL_EXHAUSTED": "RESOURCE_EXHAUSTED", "OUTBOUND_LIMIT": "RESOURCE_EXHAUSTED",
    "DEADLINE_BUDGET_EXHAUSTED": "DEADLINE_EXCEEDED", "BODY_TOO_LARGE": "INVALID_ARGUMENT",
    "RANGE_COLD": "FAILED_PRECONDITION", "UNIT_SEALED": "FAILED_PRECONDITION",
    "RATE_LIMITED": "RESOURCE_EXHAUSTED", "UPSTREAM_UNAVAILABLE": "UNAVAILABLE", "UPSTREAM_TIMEOUT": "DEADLINE_EXCEEDED",
    "NETWORK_IN_TX": "INTERNAL", "DB_TOO_MANY_CONNECTIONS": "UNAVAILABLE", "NESTED_TX": "INTERNAL",
    "REQUEST_INVALID": "INVALID_ARGUMENT", "DEPENDENCY_UNAVAILABLE": "UNAVAILABLE", "REQUEST_CANCELLED": "CANCELLED",
}
REASON_RE = re.compile(r"[A-Z][A-Z0-9]*(_[A-Z0-9]+)*")


class ErrError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def http_of(code, reason=None, domain=None):
    if code not in HTTP:
        raise ErrError("CODE_UNKNOWN")
    if reason == "BODY_TOO_LARGE" and domain == "be":
        return 413
    return HTTP[code]


def restore(inp):
    st, pb = inp["status"], inp.get("problem")
    if pb and pb.get("code") in HTTP and pb.get("reason") and pb.get("domain"):
        return {"code": pb["code"], "reason": pb["reason"], "domain": pb["domain"], "http": st}
    if st in FROM_HTTP:
        code = FROM_HTTP[st]
    elif 400 <= st < 500:
        code = "FAILED_PRECONDITION"
    else:
        code = "UNKNOWN"
    return {"code": code, "reason": None, "domain": None, "http": st}


def sqlstate(inp):
    s, attempt, ctx = inp["sqlstate"], inp.get("attempt", 1), inp.get("context", "none")
    if s in ("40001", "40P01"):
        if attempt < 3:
            return {"action": "retry", "base_delay_ms": 10 * 2 ** (attempt - 1)}
        return {"action": "fail", "code": "ABORTED", "reason": "TX_CONFLICT", "domain": "be", "http": 409}
    if s == "55P03":
        return {"action": "fail", "code": "ABORTED", "reason": "LOCK_TIMEOUT", "domain": "be", "http": 409}
    if s == "57014":
        if ctx == "cancelled":
            return {"action": "fail", "code": "CANCELLED", "reason": "REQUEST_CANCELLED", "domain": "be", "http": 499}
        return {"action": "fail", "code": "DEADLINE_EXCEEDED", "reason": "STATEMENT_TIMEOUT", "domain": "be", "http": 504}
    if s == "25P04":
        return {"action": "fail", "code": "DEADLINE_EXCEEDED", "reason": "STATEMENT_TIMEOUT", "domain": "be", "http": 504}
    if s[:2] == "08" or s in ("57P01", "57P02", "57P03"):
        # the connection could not be made or was lost: DEPENDENCY_UNAVAILABLE naming the database (P4)
        return {"action": "fail", "code": "UNAVAILABLE", "reason": "DEPENDENCY_UNAVAILABLE", "domain": "be", "http": 503,
                "metadata": {"dependency": "db"}}
    if s == "53300":
        return {"action": "fail", "code": "UNAVAILABLE", "reason": "DB_TOO_MANY_CONNECTIONS", "domain": "be", "http": 503}
    if s == "23505" and inp.get("component_mapping"):
        m = inp["component_mapping"]
        return {"action": "fail", "code": m["code"], "reason": m["reason"], "domain": m["domain"], "http": HTTP[m["code"]]}
    return {"action": "fail", "code": "INTERNAL", "reason": "INTERNAL", "domain": "be", "http": 500}


def level(code, ctx="none"):
    if code in HIDDEN:
        return "error"
    if code in ("UNAVAILABLE", "DEADLINE_EXCEEDED"):
        return "warn"
    if code == "CANCELLED":
        return "none"
    if code == "OK":
        return "none"
    return "info"


def access_level(code):
    # P4.6: the access-log line's level, by the response's code
    if code in HIDDEN:
        return "error"
    if code in ("UNAVAILABLE", "DEADLINE_EXCEEDED"):
        return "warn"
    return "info"


def problem(inp):
    e, rq = inp["error"], inp["request"]
    code = e.get("code") or "INTERNAL"  # an error the SDK does not recognise is INTERNAL (P4.3)
    if code not in HTTP or code == "OK":
        raise ErrError("CODE_UNKNOWN")
    hidden = code in HIDDEN or not e.get("reason") or not e.get("domain")
    if hidden:
        code = code if code in HIDDEN else "INTERNAL"
        reason, domain, meta, viol = "INTERNAL", "be", {}, None
    else:
        reason, domain, meta, viol = e["reason"], e["domain"], dict(e.get("metadata") or {}), e.get("violations")
    for k, v in meta.items():
        if not isinstance(v, str):
            raise ErrError("METADATA_NOT_STRING")
    body = {"type": f"urn:be:{domain}:{reason}", "status": http_of(code, reason, domain), "code": code,
            "reason": reason, "domain": domain, "metadata": meta, "instance": rq["path"],
            "request_id": rq["request_id"], "trace_id": rq["trace_id"]}
    if viol:
        body["violations"] = viol
    out = {"content_type": "application/problem+json", "body": body}
    secret = e.get("internal_message")
    if hidden and secret:
        out["detail_must_not_contain"] = [secret]
    return out


def retry_after(inp):
    code, ms = inp["code"], inp.get("retry_delay_ms", 0)
    if code not in ("RESOURCE_EXHAUSTED", "UNAVAILABLE") or ms <= 0:
        return {"header": None}
    return {"header": str(math.ceil(ms / 1000))}


def reason_ok(inp):
    r, d = inp["reason"], inp["domain"]
    if not isinstance(r, str) or not REASON_RE.fullmatch(r):
        raise ErrError("REASON_NAME_INVALID")
    if d != "be" and r in BE_REASONS:
        raise ErrError("REASON_RESERVED")
    return {"valid": True}


def add(c, slug, why, op, inp, fn, refs):
    try:
        c.add(slug, why, op, inp, expected=fn(inp), refs=refs)
    except ErrError as e:
        c.add(slug, why, op, inp, error=e.reason, refs=refs)


def gen_codes():
    c = CaseList("errors", "codes")
    for i, code in enumerate(CODES):
        add(c, code.lower().replace("_", "-"), f"{code} on the wire", "grpc_to_http", {"code": code},
            lambda inp, i=i: {"number": i, "http": http_of(inp["code"])}, ["P4.2"])
    add(c, "body-too-large", "BODY_TOO_LARGE is INVALID_ARGUMENT answered as 413", "grpc_to_http",
        {"code": "INVALID_ARGUMENT", "reason": "BODY_TOO_LARGE", "domain": "be"},
        lambda inp: {"number": 3, "http": http_of(inp["code"], inp["reason"], inp["domain"])}, ["P3.6", "P4.2"])
    add(c, "unknown-code", "not a canonical code name", "grpc_to_http", {"code": "NOT_A_CODE"},
        lambda inp: {"http": http_of(inp["code"])}, ["P4.2"])
    add(c, "lower-case-code", "code names are upper case", "grpc_to_http", {"code": "not_found"},
        lambda inp: {"http": http_of(inp["code"])}, ["P4.2"])
    for r, code in BE_REASONS.items():
        add(c, "be-" + r.lower().replace("_", "-"), f"platform reason {r}", "be_reason", {"reason": r},
            lambda inp: {"code": BE_REASONS[inp["reason"]], "domain": "be",
                         "http": http_of(BE_REASONS[inp["reason"]], inp["reason"], "be")}, ["P4"])
    for slug, inp, why in [
        ("problem-kept", {"status": 400, "problem": {"code": "FAILED_PRECONDITION", "reason": "INSUFFICIENT_STOCK",
                                                     "domain": "erp/inventory"}}, "a dependency's problem+json is kept as it is"),
        ("problem-be-kept", {"status": 403, "problem": {"code": "PERMISSION_DENIED", "reason": "MISSING_PERMISSION",
                                                        "domain": "be"}}, "a platform reason is kept"),
        ("problem-413", {"status": 413, "problem": {"code": "INVALID_ARGUMENT", "reason": "BODY_TOO_LARGE", "domain": "be"}},
         "413 with its problem body"),
        ("no-problem-400", {"status": 400, "problem": None}, "no problem body: code from the status"),
        ("no-problem-409", {"status": 409, "problem": None}, "409 without a body is ABORTED"),
        ("no-problem-418", {"status": 418, "problem": None}, "an unlisted 4xx"),
        ("no-problem-502", {"status": 502, "problem": None}, "a gateway error"),
        ("no-problem-500", {"status": 500, "problem": None}, "a bare 500"),
        ("no-problem-507", {"status": 507, "problem": None}, "an unlisted 5xx"),
        ("problem-without-reason", {"status": 404, "problem": {"code": "NOT_FOUND"}}, "a problem body missing reason and domain"),
    ]:
        add(c, "restore-" + slug, why, "restore_http", inp, restore, ["P8.2", "P4.2"])
    return c


def gen_sqlstate():
    c = CaseList("errors", "sqlstate")
    for slug, inp, why in [
        ("serialization-1", {"sqlstate": "40001", "attempt": 1}, "first attempt: retry after 10 ms (+ jitter)"),
        ("serialization-2", {"sqlstate": "40001", "attempt": 2}, "second attempt: retry after 20 ms (+ jitter)"),
        ("serialization-3", {"sqlstate": "40001", "attempt": 3}, "third attempt fails: TX_CONFLICT"),
        ("deadlock-1", {"sqlstate": "40P01", "attempt": 1}, "a deadlock is retried like 40001"),
        ("deadlock-3", {"sqlstate": "40P01", "attempt": 3}, "attempts exhausted"),
        ("lock-timeout", {"sqlstate": "55P03"}, "lock_timeout: not retried"),
        ("statement-timeout", {"sqlstate": "57014", "context": "none"}, "statement_timeout"),
        ("statement-timeout-deadline", {"sqlstate": "57014", "context": "deadline_exceeded"}, "the request deadline cancelled the statement"),
        ("query-cancelled", {"sqlstate": "57014", "context": "cancelled"}, "the caller went away: CANCELLED, not a timeout"),
        ("transaction-timeout", {"sqlstate": "25P04"}, "transaction_timeout (PostgreSQL 17+)"),
        ("idle-in-transaction", {"sqlstate": "25P03"}, "idle_in_transaction_session_timeout: a component bug"),
        ("too-many-connections", {"sqlstate": "53300"}, "the server refused a connection"),
        ("connection-failure", {"sqlstate": "08006"}, "the connection was lost: DEPENDENCY_UNAVAILABLE, dependency db"),
        ("cannot-connect", {"sqlstate": "08001"}, "the client could not establish a connection"),
        ("connection-exception", {"sqlstate": "08000"}, "any other connection exception"),
        ("admin-shutdown", {"sqlstate": "57P01"}, "the server is shutting down (a restart or failover)"),
        ("crash-shutdown", {"sqlstate": "57P02"}, "the server crashed"),
        ("cannot-connect-now", {"sqlstate": "57P03"}, "the server is starting up or in recovery"),
        ("unique-unmapped", {"sqlstate": "23505"}, "a unique violation the component did not map"),
        ("unique-mapped", {"sqlstate": "23505", "component_mapping": {"code": "ALREADY_EXISTS", "reason": "WIDGET_ALREADY_EXISTS",
                                                                      "domain": "conformance/widget"}},
         "a unique violation the component maps to its own reason"),
        ("insufficient-privilege", {"sqlstate": "42501"}, "a revoked grant: generic INTERNAL, no SQL text"),
        ("undefined-table", {"sqlstate": "42P01"}, "a missing table"),
        ("invalid-text", {"sqlstate": "22P02"}, "invalid input syntax reached the database"),
    ]:
        add(c, slug, why, "classify", inp, sqlstate, ["P10.4"])
    return c


def gen_levels():
    c = CaseList("errors", "levels")
    for code in CODES:
        add(c, code.lower().replace("_", "-"), f"log level of {code}", "log_level", {"code": code},
            lambda inp: {"level": level(inp["code"])}, ["P4.6"])
    for code in CODES:
        add(c, "access-" + code.lower().replace("_", "-"), f"access-log line level of a response with code {code}",
            "access_log_level", {"code": code}, lambda inp: {"level": access_level(inp["code"])}, ["P4.6", "P3.10"])
    return c


def gen_problem():
    c = CaseList("errors", "problem")
    rq = {"path": "/conformance/widget/widgets/0192f0c5-1111-7000-8000-000000000001/approve",
          "request_id": "r-1", "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"}
    for slug, err, why in [
        ("component-reason", {"code": "FAILED_PRECONDITION", "reason": "WIDGET_NOT_DRAFT", "domain": "conformance/widget",
                              "metadata": {"status": "APPROVED"}}, "a component's own reason"),
        ("relayed-reason", {"code": "FAILED_PRECONDITION", "reason": "QUOTA_EXCEEDED", "domain": "conformance/peer",
                            "metadata": {"requested": "5", "available": "2"}}, "a dependency's reason relayed with its domain"),
        ("violations", {"code": "INVALID_ARGUMENT", "reason": "WIDGET_INVALID", "domain": "conformance/widget",
                        "violations": [{"field": "lines[0].quantity", "reason": "MUST_BE_POSITIVE", "description": "quantity must be > 0"}]},
         "field violations from BadRequest"),
        ("platform-reason", {"code": "PERMISSION_DENIED", "reason": "MISSING_PERMISSION", "domain": "be",
                             "metadata": {"permission": "conformance.widget.approve"}}, "a platform reason"),
        ("body-too-large", {"code": "INVALID_ARGUMENT", "reason": "BODY_TOO_LARGE", "domain": "be",
                            "metadata": {"limit": "1048576"}}, "413"),
        ("internal-hidden", {"code": "INTERNAL", "reason": "DB_BROKE", "domain": "conformance/widget",
                             "metadata": {"table": "widgets"},
                             "internal_message": "ERROR: permission denied for table widgets (SQLSTATE 42501)"},
         "INTERNAL hides reason, domain, metadata and the message"),
        ("unknown-hidden", {"code": "UNKNOWN", "internal_message": "panic: runtime error: index out of range"},
         "UNKNOWN is answered like INTERNAL"),
        ("data-loss-hidden", {"code": "DATA_LOSS", "reason": "X", "domain": "conformance/widget", "internal_message": "checksum mismatch"},
         "DATA_LOSS is answered like INTERNAL"),
        ("network-in-tx-hidden", {"code": "INTERNAL", "reason": "NETWORK_IN_TX", "domain": "be",
                                  "internal_message": "outbound call conformance.peer.v1.PeerService/Reserve inside a transaction"},
         "NETWORK_IN_TX is a reason of code INTERNAL: the caller sees only the generic INTERNAL body"),
        ("request-invalid", {"code": "INVALID_ARGUMENT", "reason": "REQUEST_INVALID", "domain": "be",
                             "violations": [{"field": "lines[0].quantity", "reason": "DECIMAL_INVALID", "description": "not a decimal string"}]},
         "the request does not match the operation's schema"),
        ("dependency-unavailable", {"code": "UNAVAILABLE", "reason": "DEPENDENCY_UNAVAILABLE", "domain": "be",
                                    "metadata": {"dependency": "db"}}, "PostgreSQL could not be reached"),
        ("dependency-unavailable-peer", {"code": "UNAVAILABLE", "reason": "DEPENDENCY_UNAVAILABLE", "domain": "be",
                                         "metadata": {"dependency": "conformance/peer"}}, "a dependency refused the connection"),
        ("request-cancelled", {"code": "CANCELLED", "reason": "REQUEST_CANCELLED", "domain": "be"}, "the caller went away: 499"),
        ("unclassified", {"internal_message": "unexpected end of input"},
         "an error with no code and no reason becomes INTERNAL"),
        ("reason-without-domain", {"code": "NOT_FOUND", "reason": "WIDGET_GONE", "internal_message": "row missing"},
         "a reason without a domain is not trusted: INTERNAL"),
        ("metadata-number", {"code": "FAILED_PRECONDITION", "reason": "WIDGET_NOT_DRAFT", "domain": "conformance/widget",
                             "metadata": {"version": 3}}, "metadata values are strings only"),
    ]:
        add(c, slug, why, "problem", {"error": err, "request": rq}, problem, ["P4.1", "P4.3"])
    for slug, inp, why in [
        ("retry-429", {"code": "RESOURCE_EXHAUSTED", "retry_delay_ms": 1500}, "rounded up to whole seconds"),
        ("retry-503", {"code": "UNAVAILABLE", "retry_delay_ms": 100}, "less than a second is 1"),
        ("retry-503-exact", {"code": "UNAVAILABLE", "retry_delay_ms": 3000}, "exactly 3 s"),
        ("retry-none", {"code": "UNAVAILABLE"}, "no delay, no header"),
        ("retry-400", {"code": "INVALID_ARGUMENT", "retry_delay_ms": 1000}, "only with 429 and 503"),
    ]:
        add(c, slug, why, "retry_after", inp, retry_after, ["P4"])
    for slug, inp, why in [
        ("name-ok", {"reason": "INSUFFICIENT_STOCK", "domain": "erp/inventory"}, "UPPER_SNAKE"),
        ("name-digits", {"reason": "PHASE2_FAILED", "domain": "erp/inventory"}, "digits allowed"),
        ("name-lower", {"reason": "insufficient_stock", "domain": "erp/inventory"}, "lower case"),
        ("name-leading-digit", {"reason": "2FA_REQUIRED", "domain": "infra/iam"}, "leading digit"),
        ("name-double-underscore", {"reason": "A__B", "domain": "erp/inventory"}, "empty word"),
        ("name-trailing-underscore", {"reason": "NOT_DRAFT_", "domain": "erp/sales"}, "trailing underscore"),
        ("name-hyphen", {"reason": "NOT-DRAFT", "domain": "erp/sales"}, "hyphen"),
        ("reserved-in-component", {"reason": "NOT_FOUND", "domain": "erp/sales"}, "a platform name raised in a component's domain"),
        ("reserved-in-be", {"reason": "NOT_FOUND", "domain": "be"}, "the platform raises its own names"),
    ]:
        add(c, slug, why, "reason_name", inp, reason_ok, ["P4.1", "P4.4"])
    return c


def main():
    counts = {}
    for topic, fn in [("codes", gen_codes), ("sqlstate", gen_sqlstate), ("levels", gen_levels), ("problem", gen_problem)]:
        counts[topic] = write_file(os.path.join(OUT, f"{topic}.json"), "errors", topic, GEN, fn())
    print("errors", counts, "total", sum(counts.values()))


if __name__ == "__main__":
    main()
