[English](README.md) · [中文](README.zh.md)

# Vectors: errors

The error model's computable parts (protocol P4, P10.4; foundations 10, 15, 23): code ↔ status, platform reasons, restoring a dependency's REST error, SQLSTATE classification, log levels, the problem+json body, `Retry-After`, reason names. SDK API: the HTTP `Fail` path, the gRPC error interceptor, `UserHTTP`'s error decoding, the `Store.Tx` retry loop, the log handler.

## Files

| File | Cases | Operations |
|---|---|---|
| `codes.json` | 66 | `grpc_to_http`, `be_reason`, `restore_http` |
| `sqlstate.json` | 23 | `classify` |
| `levels.json` | 34 | `log_level`, `access_log_level` |
| `problem.json` | 30 | `problem`, `retry_after`, `reason_name` |

## Operations

| Op | Input | Expected |
|---|---|---|
| `grpc_to_http` | `code` (canonical name), optional `reason`, `domain` | `number` (the gRPC numeric code), `http` |
| `be_reason` | `reason` (a platform reason) | `code`, `domain: be`, `http` |
| `restore_http` | `status`, `problem` (the dependency's problem+json members, or `null`) | `code`, `reason`, `domain`, `http` as the caller sees the error |
| `classify` | `sqlstate`, `attempt` (1-based, for retryable states), `context` (`none`, `deadline_exceeded`, `cancelled`), `component_mapping` (a 23505 the component maps) | `action: retry` with `base_delay_ms`, or `action: fail` with `code`, `reason`, `domain`, `http`, and `metadata` when the reason has parameters |
| `log_level` | `code` | `level`: `error`, `warn`, `info` or `none` |
| `access_log_level` | `code` (of the response) | `level` of the access-log line: `error`, `warn` or `info` |
| `problem` | `error` (`code`, `reason`, `domain`, `metadata`, `violations`, `internal_message`), `request` (`path`, `request_id`, `trace_id`) | `content_type`, `body` (every member except `title` and `detail`, which come from the catalogue), and `detail_must_not_contain[]` |
| `retry_after` | `code`, `retry_delay_ms` | `header`: the `Retry-After` value, or `null` |
| `reason_name` | `reason`, `domain` | `valid: true` |

## Rules

- **Code → status**: the foundations 15 table: 400 for `INVALID_ARGUMENT`, `FAILED_PRECONDITION`, `OUT_OF_RANGE`; 401, 403, 404; 409 for `ALREADY_EXISTS`, `ABORTED`; 429; 499 `CANCELLED`; 500 for `INTERNAL`, `UNKNOWN`, `DATA_LOSS`; 501, 503, 504. The single exception: `be` / `BODY_TOO_LARGE` is `INVALID_ARGUMENT` answered as **413**.
- **Restoring a REST error**: a problem body with a known `code`, a `reason` and a `domain` is kept exactly. Without one, the code comes from the status (400, 413 → `INVALID_ARGUMENT`; 401; 403; 404; 409 → `ABORTED`; 429; 499; 501; 502, 503 → `UNAVAILABLE`; 504; any other 4xx → `FAILED_PRECONDITION`; any other 5xx → `UNKNOWN`) and `reason` / `domain` are `null`.
- **SQLSTATE**: `40001`, `40P01` re-run the transaction body after `10 ms · 2^(attempt−1)` plus jitter, for at most 3 attempts in all; the third failure is `ABORTED` / `TX_CONFLICT`. `55P03` → `ABORTED` / `LOCK_TIMEOUT`. `57014` → `DEADLINE_EXCEEDED` / `STATEMENT_TIMEOUT`, except when the request itself was cancelled (`CANCELLED` / `REQUEST_CANCELLED`, 499). `25P04` → `STATEMENT_TIMEOUT`. `53300` → `UNAVAILABLE` / `DB_TOO_MANY_CONNECTIONS`. A lost or refused connection (class `08`, `57P01`, `57P02`, `57P03`) → `UNAVAILABLE` / `DEPENDENCY_UNAVAILABLE` with `metadata.dependency = db`. A `23505` the component maps keeps the component's reason. Everything else, `25P03` and `42501` included, is `INTERNAL`.
- **Levels**: `INTERNAL`, `UNKNOWN`, `DATA_LOSS` → error; `UNAVAILABLE`, `DEADLINE_EXCEEDED` → warn; `CANCELLED` and `OK` → not logged; every caller error → info. The access-log line of a response: error for the three hidden codes, warn for `UNAVAILABLE` and `DEADLINE_EXCEEDED`, info for everything else, `OK` and `CANCELLED` included.
- **problem+json**: `type` = `urn:be:<domain>:<reason>`; `status` from the table; `code` the canonical name; `instance` the path; `request_id` and `trace_id` always. `INTERNAL`, `UNKNOWN` and `DATA_LOSS`, an error without a code, and an error with a reason but no domain, all answer `reason: INTERNAL`, `domain: be`, empty `metadata`, no `violations`, and a `detail` that contains none of the original message (`UNKNOWN` and `DATA_LOSS` keep their own `code`). `metadata` values are strings only.
- **Retry-After**: only with 429 and 503, only when the error carries a delay; whole seconds, rounded up.
- **Reason names**: `^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$`; a component never raises a platform reason name in its own domain.

## Errors

| Class | When |
|---|---|
| `CODE_UNKNOWN` | not a canonical code name (names are upper case) |
| `METADATA_NOT_STRING` | a `metadata` value that is not a string |
| `REASON_NAME_INVALID`, `REASON_RESERVED` | a reason that breaks the naming rule, or reuses a platform name outside `domain: be` |

## Decided here

For review: the status → code table used when a dependency answers without a problem body (no reason invented: `null`); `57014` on a cancelled request maps to `CANCELLED` / `REQUEST_CANCELLED` (rc.2: every error the runtime answers has a reason); an error with a reason but no domain is treated as unclassified; `UNKNOWN` / `DATA_LOSS` keep their code while their reason becomes `INTERNAL`; the platform's own `type` is `urn:be:be:<REASON>`; `title` and `detail` texts are not pinned here because they come from the catalogues (`schemas/errors-be.yaml`, each component's `contracts/errors.yaml`).

## Regenerate

`python3 gen/gen_errors.py`; cross-check `go run gen/xcheck_errors.go .`.
