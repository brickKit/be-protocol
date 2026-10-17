"""Chapter 03: the error catalog (P3.9)."""
from common import write


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
    ("AUDIT_CAPACITY_EXHAUSTED", "UNAVAILABLE", None, "yes"),
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
