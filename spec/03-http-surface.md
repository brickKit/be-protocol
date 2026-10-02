[English](03-http-surface.md) · [中文](03-http-surface.zh.md)

# P3 HTTP surface

What a component serves on its main port: the three kinds of path, the request and response headers every exchange carries, deadlines, server timeouts, body limits, idempotency keys, paging and versioning. Errors are in [P4](04-errors.md), authorization in [P6](06-authorization.md).

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P3.1 | MUST | The main port serves three kinds of path and nothing else: **user plane** `/{domain}/{name}/…` (routed by the edge, declared in `edge_routes`); **operations** `/healthz`, `/readyz`, `/metrics`, `/_be/info` (never routed by the edge); **resource contract** `/{domain}/{name}/_authz/*`, `/{domain}/{name}/_shares/*`, `/{domain}/{name}/_lifecycle/*`, `/{domain}/{name}/_ops/*` (routed by the edge, [P6.10](06-authorization.md), [P16.4](16-data-lifecycle.md), [P14.4](14-background-jobs.md)). The mobile BFF is the one exception: its user plane is `/graphql` | CP-CORE-11 |
| P3.2 | MUST | Request ID: an inbound `X-Request-Id` is kept (the edge strips a client-forged one); when absent, the trace ID is used. Every response carries `X-Request-Id`; every outbound call carries it ([P7.2](07-system-rpc.md), [P8.1](08-outbound-http.md)) | CP-CORE-10 |
| P3.3 | MUST | Trace: inbound W3C `traceparent`, `tracestate` and `baggage` are extracted; the request's server span is a child of the caller's span ([P18.1](18-observability.md)) | CP-OBS-01 |
| P3.4 | MUST | Every route has a deadline: `HTTP_DEFAULT_TIMEOUT` (default 10 s) unless the route declares its own (P3.13); an orchestrating route declares 15 s; exports are asynchronous and never hold a synchronous route. When the deadline passes, the downstream calls and the open transaction of the request are cancelled and the component answers `504`, code `DEADLINE_EXCEEDED`, with reason `STATEMENT_TIMEOUT` when a database statement was cancelled, the downstream's own reason when a dependency answered `DEADLINE_EXCEEDED` with an `ErrorInfo`, and `DEADLINE_BUDGET_EXHAUSTED` otherwise | CP-OUT-07, CP-DB-02 |
| P3.5 | MUST | Server timeouts: read request headers 5 s; read the whole request 30 s; write the response = route deadline + 5 s; idle keep-alive connection 120 s. A client that sends headers slowly is disconnected; the header timeout is enforced with at most 1 s granularity, so the cut comes within 6 s. A route's handler is bounded by its deadline (P3.4): when it runs past it, the answer is `504` `DEADLINE_EXCEEDED`, never a dropped connection | CP-CORE-08 |
| P3.6 | MUST | Request bodies are limited to 1 MiB unless the route declares more. A larger body answers `413` with reason `BODY_TOO_LARGE`. Files never travel through a component's body: uploads use presigned object-storage URLs ([P17](17-object-storage.md)) | CP-CORE-09 |
| P3.7 | MUST | A write command accepts its idempotency key either as the request header `Idempotency-Key` or as the body field `idempotency_key`; the two are equivalent. Both present with different values answers `400` with reason `IDEMPOTENCY_MISMATCH` ([P13](13-idempotency.md)) | CP-IDEM-08 |
| P3.8 | MUST | Lists page by cursor (AIP-158): request parameters `page_size` and `cursor`; response field `next_cursor`, empty at the end. `page_size` defaults to 50; above the endpoint's cap (at most 500) it is lowered to the cap, never refused. The cursor is opaque: it encodes the sort key, the last ID and a hash of the filters; a cursor sent with different filters answers `400` `CURSOR_INVALID`. No `offset`, no exact totals. Default order `created_at DESC, id DESC` | — |
| P3.9 | SHOULD | `List` and `Get` of a view derived from another component's events (projections, snapshots, ACLs) carry `X-Data-As-Of`: the `occurred_at` of the newest event that view has applied, RFC 3339 | — |
| P3.10 | MUST | One access-log line per request, `msg` = `http_request`, with the fields in [P18.2](18-observability.md) | CP-OBS-02 |
| P3.11 | MUST | No CORS handling in the component: same origin by default, cross-origin policy belongs to the edge | — |
| P3.12 | MUST | `/metrics` serves the Prometheus text format ([P18.3](18-observability.md)); `/_be/info` serves the self-description ([P20](20-self-description-and-versioning.md)) | CP-OBS-03, CP-CORE-11 |
| P3.13 | MUST | A route's own deadline and body limit are declared on its OpenAPI operation as `x-be-deadline-seconds` (integer) and `x-be-max-body-bytes` (integer), so the edge, the server and the frontend read one number. Absent means the defaults of P3.4 and P3.6 | — |
| P3.14 | MUST | Within a major version a component's operations only grow. A breaking change publishes new operations under `/{domain}/{name}/v2/…` beside the old ones; the old operations answer with `Deprecation`, `Sunset` and `Link: <…>; rel="successor-version"` until the sunset date | — |
| P3.15 | MUST | Status codes for access follow [P6.6](06-authorization.md): `401` for missing, invalid or stale tokens; `403` only when the record is visible but the action is not allowed; `404` for a record that does not exist **or is not visible**, for reads and commands alike | CP-SCOPE-07, CP-SCOPE-08 |

## Request headers

| Header | Meaning |
|---|---|
| `Authorization: Bearer <token>` | the user's access token ([P5](05-identity.md)) |
| `Idempotency-Key` | for writes; equal to the body's `idempotency_key` when both are present ([P13](13-idempotency.md)) |
| `X-Request-Id` | optional; generated when absent |
| `traceparent`, `tracestate`, `baggage` | W3C trace context, normally created at the edge |
| `X-Authz-Revision` | the authorization consistency token ([P6.11](06-authorization.md)) |

`Accept-Language` is not used to choose error text ([P4](04-errors.md)).

## Response headers

| Header | When |
|---|---|
| `X-Request-Id` | always |
| `Content-Type: application/problem+json` | every 4xx and 5xx ([P4.1](04-errors.md)) |
| `X-Data-As-Of` | reads of a derived view (P3.9) |
| `Retry-After` | with `429` and `503` when the error carries a retry delay (gRPC `RetryInfo`) |
| `X-Authz-Consistency: stale` | a list filtered with a projection behind the requested revision ([P6.11](06-authorization.md)) |
| `X-Authz-Degraded: graph` | a list whose graph branch was skipped because the provider lacks `graph` ([P6](06-authorization.md)) |
| `WWW-Authenticate: Bearer error="token_stale"` | `401 TOKEN_STALE` ([P5.6](05-identity.md)) |
| `Deprecation`, `Sunset`, `Link` | an operation scheduled for removal (P3.14) |

## List shape

```json
{ "items": [ … ], "next_cursor": "eyJr…" }
```

The array's field name is the contract's (`items`, `orders`, …); `next_cursor` is fixed. Rows of a resource list carry `_access` ([P6.9](06-authorization.md)) and `_masked` ([P6.8](06-authorization.md)) when those apply.

## Notes

- The deadline in P3.4 is the root of the budget that every lower layer shrinks ([P9](09-deadlines-and-retries.md)).
- A `page_size` above the cap is lowered rather than refused so that a client written against a larger cap keeps working.
