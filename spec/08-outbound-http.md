[English](08-outbound-http.md) · [中文](08-outbound-http.zh.md)

# P8 Outbound HTTP: user plane and third parties

Two kinds of outbound HTTP besides gRPC: a call to another component's REST user plane on behalf of the current user, and a call to a third party (DingTalk, Casdoor and similar). Plus the rule that no network call happens inside a transaction.

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P8.1 | MUST | User-plane HTTP to another component is made only with a user in the context. It forwards the caller's original `Authorization` header unchanged, plus `X-Request-Id`, `traceparent`, `tracestate`, `baggage` and `X-Authz-Revision` when present. With no user in the context (an event handler, a job, a gRPC system call) it fails with `UNAUTHENTICATED`; it never silently switches to a system identity | CP-OUT-06 |
| P8.2 | MUST | User-plane HTTP uses the outbound deadline of [P7.7](07-system-rpc.md) and the bulkhead of [P7.9](07-system-rpc.md). Only `GET` is retried, once, and only on a connection reset. A problem+json answer is restored as the same status code, `reason` and `domain` | CP-OUT-06 |
| P8.3 | MUST | Third-party HTTP: default timeout 10 s, configurable per named client by a key of the component's own; traced, and counted in `be_http_client_requests_total` / `be_http_client_duration_seconds` (labels `target` = the client name, `method`, `status_code`); user-plane HTTP (P8.1) is counted in the same pair with `target` = the dependency's component ID. It forwards **no** internal header: not `Authorization`, not `be-*`, not `X-Authz-*`, not `X-Request-Id`. The W3C `traceparent` MAY be sent | — |
| P8.4 | INTERNAL | No network inside a transaction: while the current unit of work holds an open transaction, every outbound call the runtime offers (gRPC, user-plane HTTP, third-party HTTP, a direct publish to the bus) refuses to start and fails as `INTERNAL`; in test builds it aborts the test. The only ways to cause an outside effect from a transaction are an outbox row ([P12.1](12-events.md)) and a queued job ([P14](14-background-jobs.md)) | — |

## Notes

- P8.1 is the user plane's half of [P7.1](07-system-rpc.md): data filtered by the user's scope is read with the user's own token, so the callee decides with its own rules.
- The transaction guard of P8.4 travels with the call's context, not with the process, so it holds per member in a shell.
- The pair `be_http_client_requests_total` / `be_http_client_duration_seconds` is also listed in [P18.3](18-observability.md).
