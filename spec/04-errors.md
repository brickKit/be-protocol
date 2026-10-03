[English](04-errors.md) · [中文](04-errors.zh.md)

# P4 Errors

One error object across REST, gRPC and GraphQL: RFC 9457 problem details carrying the members of Google AIP-193's `ErrorInfo` (`reason`, `domain`, `metadata`), a catalogue of reasons per component, and the reserved reasons of domain `be`. Schemas: [`problem.schema.json`](../schemas/problem.schema.json), [`errors-yaml.schema.json`](../schemas/errors-yaml.schema.json); catalogue: [`errors-be.yaml`](../schemas/errors-be.yaml).

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P4.1 | MUST | Every `4xx` and `5xx` REST response of a component has `Content-Type: application/problem+json` and the body below; every one the runtime produces carries a reason, so no error leaves without `reason` and `domain`. `reason` is `UPPER_SNAKE`. `domain` is the component ID unchanged (`erp/inventory`), or `be` for a reserved reason; the members of a slot family use the family's ID instead of their own (every authorization member answers `domain: infra/authz`), so the frontend keeps one table per family. `type` is `urn:be:<domain>:<reason>`. There is no `error` field and no `retry_after_ms` field: a retry delay travels only in the `Retry-After` header | CP-ERR-01 |
| P4.2 | MUST | On gRPC an error is a standard status code with the default-language `detail` as its message, plus `google.rpc.ErrorInfo{reason, domain, metadata}` always, and `BadRequest`, `PreconditionFailure`, `RetryInfo`, `ResourceInfo` when they apply. REST and gRPC map both ways with the table below, so a component that calls another over gRPC and answers its user over REST loses nothing. `LocalizedMessage` is not used | CP-ERR-02 |
| P4.3 | MUST | `INTERNAL`, `UNKNOWN` and `DATA_LOSS` always answer `reason: INTERNAL`, `domain: be`, a generic `detail` and the `trace_id`. The original error (SQL text, a stack, a token parser's message) goes only to the log. Component code cannot opt out | CP-ERR-03 |
| P4.4 | MUST | Each component lists its own reasons in `contracts/errors.yaml` ([format](../schemas/errors-yaml.schema.json)): `{reason, code, http, params[], title{zh,en}, message{zh,en}, since, deprecated}`. Entries are append-only: never renamed, removed or reused; retired with `deprecated: true`. Every reason a component raises in its own domain is listed there (a slot-family member's reasons are listed in its family contract's `errors.yaml`); a reason of domain `be` is listed in `errors-be.yaml`; a reason relayed from a dependency keeps that dependency's `domain` and is listed in the dependency's catalogue (P4.9). The frontend translates from the catalogues; the server does not translate | CP-ERR-04 |
| P4.5 | MUST | GraphQL (the mobile BFF): `errors[].extensions = {code, reason, domain, metadata, request_id, trace_id}`, copied from the downstream error | CP-ERR-01 |
| P4.6 | MUST | The runtime decides the log level of an error from its code: `INTERNAL`, `UNKNOWN`, `DATA_LOSS` → ERROR; `UNAVAILABLE`, `DEADLINE_EXCEEDED` → WARN; `CANCELLED`, including a cancel during shutdown → not logged as an error; every caller error (`INVALID_ARGUMENT`, `NOT_FOUND`, `PERMISSION_DENIED`, `FAILED_PRECONDITION`, `UNAUTHENTICATED`, …) → INFO. The access-log line of a request ([P3.10](03-http-surface.md)) takes its level from the same code: ERROR for `500`, WARN for `503` and `504`, INFO for everything else, including `2xx`, `4xx`, `499` and `501` (vectors `errors`, `access_log_level`) | CP-OBS-02 |
| P4.7 | MUST | A component never raises a reserved reason name in its own domain, and never raises a reason of domain `be` that is not in `errors-be.yaml` | CP-ERR-04 |
| P4.8 | MUST | `metadata` values are strings only (numbers and dates formatted by the producer); never secrets, never personal data beyond what the caller sent | CP-ERR-01 |
| P4.9 | SHOULD | Relaying a dependency's error: keep its `reason` and `domain` when they mean something to the user (insufficient stock); map to a reason of one's own only when that adds meaning | — |

## The problem body

```json
{
  "type": "urn:be:erp/inventory:INSUFFICIENT_STOCK",
  "title": "Insufficient stock",
  "status": 400,
  "code": "FAILED_PRECONDITION",
  "reason": "INSUFFICIENT_STOCK",
  "domain": "erp/inventory",
  "detail": "Only 2 of product 0192… in stock, 5 requested",
  "metadata": { "product_id": "0192…", "requested": "5", "available": "2" },
  "violations": [ { "field": "items[0].qty", "reason": "MUST_BE_POSITIVE", "description": "…" } ],
  "instance": "/erp/sales/orders/0192…/confirm",
  "request_id": "…",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

| Field | Required | Rule |
|---|---|---|
| `type` | yes | `urn:be:<domain>:<reason>` |
| `title` | yes | the reason's short title in the deployment's default language, from the catalogue: `DEFAULT_LOCALE` selects `zh` or `en` by its primary language subtag; any other value falls back to `en` ([P2](02-configuration.md#protocol-keys)) |
| `status` | yes | the HTTP status |
| `code` | yes | the canonical gRPC code name |
| `reason`, `domain` | yes | the identity of the error; the frontend looks up `domain` + `reason` |
| `detail` | yes | the rendered message in `DEFAULT_LOCALE`; generic for `INTERNAL` |
| `metadata` | yes (may be `{}`) | string values, the catalogue template's parameters |
| `violations` | no | field errors, from gRPC `BadRequest` |
| `instance` | yes | the request path |
| `request_id`, `trace_id` | yes | always present |

## Code mapping

| gRPC code | HTTP | gRPC code | HTTP |
|---|---|---|---|
| `INVALID_ARGUMENT`, `FAILED_PRECONDITION`, `OUT_OF_RANGE` | 400 | `RESOURCE_EXHAUSTED` | 429 |
| `UNAUTHENTICATED` | 401 | `CANCELLED` | 499 |
| `PERMISSION_DENIED` | 403 | `UNIMPLEMENTED` | 501 |
| `NOT_FOUND` | 404 | `UNAVAILABLE` | 503 |
| `ALREADY_EXISTS`, `ABORTED` | 409 | `DEADLINE_EXCEEDED` | 504 |
| `INTERNAL`, `UNKNOWN`, `DATA_LOSS` | 500 | | |

One exception: reason `BODY_TOO_LARGE` (code `INVALID_ARGUMENT`) answers HTTP `413`. `RetryInfo` becomes `Retry-After` (whole seconds, rounded up) and back.

## Reserved reasons (domain `be`)

This is the complete set; [`errors-be.yaml`](../schemas/errors-be.yaml) carries the same rows with titles and messages in both languages.

| Reason | Code | Raised when |
|---|---|---|
| `INTERNAL` | `INTERNAL` | any internal error, original hidden |
| `TOKEN_STALE` | `UNAUTHENTICATED` | the token predates a role change |
| `MISSING_PERMISSION` | `PERMISSION_DENIED` | the caller lacks a permission key |
| `NOT_FOUND` | `NOT_FOUND` | the record does not exist or is not visible |
| `AUTHZ_NOT_READY` | `UNAVAILABLE` | the permission bundle has not loaded |
| `NOT_READY` | `UNAVAILABLE` | the process is not ready: no bundle yet, the database identity probe has not passed, or the migrations are behind the image (`/readyz`) |
| `TOKEN_INVALID` | `UNAUTHENTICATED` | no token, or one that fails verification (signature, `iss`, `aud`, `typ`, expiry) |
| `UNSUPPORTED_DELEGATION` | `UNAUTHENTICATED` | a token that acts through a kind of delegate the provider does not support |
| `MISSING_CALLER` | `UNAUTHENTICATED` | a system call without `be-caller` |
| `OUT_OF_SCOPE` | `PERMISSION_DENIED` | a request parameter that is itself a scope value outside the caller's scope (`warehouse_id=7`), or a visible record outside the scope of the action's key the caller holds |
| `FIELD_FORBIDDEN` | `PERMISSION_DENIED` | a write to a field the caller may not see |
| `SORT_FORBIDDEN` | `INVALID_ARGUMENT` | sorting, filtering or aggregating by a field masked for the caller |
| `SHARE_NOT_ALLOWED` | `PERMISSION_DENIED` | a share the resource type or the caller may not make |
| `CAPABILITY_UNAVAILABLE` | `UNIMPLEMENTED` | the installed provider or adapter lacks a capability; `metadata.capability` names it |
| `IDEMPOTENCY_MISMATCH` | `INVALID_ARGUMENT` | a key reused with another command, target or body |
| `IDEMPOTENCY_IN_PROGRESS` | `ABORTED` | the first use of the key has not finished |
| `CURSOR_INVALID` | `INVALID_ARGUMENT` | a cursor that does not match the request |
| `BATCH_TOO_LARGE` | `INVALID_ARGUMENT` | more IDs than a batch allows |
| `LOCK_TIMEOUT` | `ABORTED` | a lock wait exceeded `lock_timeout` |
| `STATEMENT_TIMEOUT` | `DEADLINE_EXCEEDED` | a statement or transaction exceeded its timeout |
| `TX_CONFLICT` | `ABORTED` | serialization failures persisted after the automatic retries |
| `DB_POOL_EXHAUSTED` | `RESOURCE_EXHAUSTED` | the member's connection budget stayed full until its deadline |
| `OUTBOUND_LIMIT` | `RESOURCE_EXHAUSTED` | too many concurrent calls to one dependency |
| `DEADLINE_BUDGET_EXHAUSTED` | `DEADLINE_EXCEEDED` | too little time left to start a call |
| `BODY_TOO_LARGE` | `INVALID_ARGUMENT` | the request body exceeds the route's limit; answered as HTTP 413 |
| `RANGE_COLD` | `FAILED_PRECONDITION` | the requested time range is in cold storage; `metadata` gives the cold ranges and whether thawing or an export is possible |
| `UNIT_SEALED` | `FAILED_PRECONDITION` | a change to a sealed lifecycle unit; correct it with a new reversing document |
| `RATE_LIMITED` | `RESOURCE_EXHAUSTED` | the edge's rate limit for the caller or route was reached; HTTP 429, with `Retry-After` |
| `UPSTREAM_UNAVAILABLE` | `UNAVAILABLE` | the edge could not reach the component; HTTP 502 or 503 (`http_also` in the catalogue) |
| `UPSTREAM_TIMEOUT` | `DEADLINE_EXCEEDED` | the component did not answer within the edge's deadline; HTTP 504 |
| `NETWORK_IN_TX` | `INTERNAL` | an outbound call (gRPC, user-plane or third-party HTTP, a direct publish) started while the unit of work holds an open transaction ([P8.4](08-outbound-http.md)); a programming error |
| `DB_TOO_MANY_CONNECTIONS` | `UNAVAILABLE` | PostgreSQL refused a new connection, SQLSTATE `53300` ([P10.4](10-database.md)); HTTP 503 |
| `NESTED_TX` | `INTERNAL` | a transaction opened while the same unit of work already holds one ([P10.6](10-database.md)); a programming error |
| `REQUEST_INVALID` | `INVALID_ARGUMENT` | the request cannot be decoded or does not match the operation's schema: malformed JSON, a wrong type, a missing required field, an unknown enum value, a path or query parameter of the wrong form, a malformed decimal string ([P11.6](11-migrations-and-data-shapes.md)); field errors in `violations` |
| `DEPENDENCY_UNAVAILABLE` | `UNAVAILABLE` | something the request needs could not be reached; `metadata.dependency` names it: `db`, `bus`, `blob`, or the ID of the component or slot family that did not answer; HTTP 503 |
| `REQUEST_CANCELLED` | `CANCELLED` | the caller cancelled the request before it finished (closed connection, cancelled gRPC call, a statement cancelled because of it); HTTP 499, never logged as an error (P4.6) |

`RATE_LIMITED`, `UPSTREAM_UNAVAILABLE` and `UPSTREAM_TIMEOUT` are raised by the edge, never by a component: answers the edge produces itself (404, 413, 429, 502, 503, 504) carry this problem body with `domain: be`.

`DEPENDENCY_UNAVAILABLE` is the runtime's answer when it cannot reach something itself: PostgreSQL refusing or dropping the connection (SQLSTATE class `08`, `57P01`, `57P02`, `57P03`; `53300` is `DB_TOO_MANY_CONNECTIONS`), the bus during a direct publish, object storage, or a dependency that refused the connection, reset it, or answered `UNAVAILABLE` without an `ErrorInfo` of its own. A dependency that answered with its own `ErrorInfo` is relayed with its `reason` and `domain` (P4.9). `UPSTREAM_UNAVAILABLE` is never raised by a component.

Internal guard failures that a black box never sees (a nested transaction, `NESTED_TX`, [P10.6](10-database.md); a network call inside a transaction, `NETWORK_IN_TX`, [P8.4](08-outbound-http.md)) are programming errors. They leave the process as the generic `INTERNAL` body (P4.3): a reason whose code is `INTERNAL` is never shown to a caller, it appears only in the log line's `error.reason`, and in a test build it aborts the test so the bug surfaces in development.

## Notes

- Machine reasons make errors testable (a test asserts `CUSTOMER_CODE_TAKEN`, not a sentence) and translatable by the frontend, which owns the user's language.
- Server-rendered text exists only where no frontend is involved (notifications, printed documents), in the recipient's `locale` ([P5.5](05-identity.md)).
