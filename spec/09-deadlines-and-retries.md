[English](09-deadlines-and-retries.md) · [中文](09-deadlines-and-retries.zh.md)

# P9 Deadlines and retry budgets

Every request has a deadline, and it only shrinks as it travels: each hop gives its children less time than it has itself. This chapter states that rule and summarises, hop by hop, the defaults the other chapters define; where a row and its source chapter differ, the source chapter is right.

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P9.1 | MUST | A child call's timeout is shorter than the time the current unit of work's own caller is still willing to wait for it. No layer extends a deadline it received | CP-OUT-02, CP-OUT-07 |
| P9.2 | MUST | One layer retries. Component code never wraps a retry loop around a runtime call that already retries; a retry a layer higher (a reconciler, a redelivered event, a frontend retry) reuses the same idempotency key | — (INTERNAL in component code) |

## The budget, hop by hop

| Hop | Default | Source |
|---|---|---|
| Edge | route deadline + 5 s | edge configuration, from the same declaration ([P3.13](03-http-surface.md)) |
| Inbound HTTP | `HTTP_DEFAULT_TIMEOUT` (10 s); 15 s for declared orchestrations | [P3.4](03-http-surface.md) |
| HTTP server | read headers 5 s, read 30 s, write = route deadline + 5 s, idle 120 s | [P3.5](03-http-surface.md) |
| Inbound gRPC | the caller's `grpc-timeout`; 10 s when absent | [P7.4](07-system-rpc.md) |
| Outbound gRPC and user-plane HTTP | `min(3 s, remaining − 50 ms)`; under 50 ms not sent | [P7.7](07-system-rpc.md), [P8.2](08-outbound-http.md) |
| Third-party HTTP | 10 s, per client | [P8.3](08-outbound-http.md) |
| SQL statement | `min(5 s, remaining)` | [P10.3](10-database.md) |
| Lock wait | 2 s | [P10.3](10-database.md) |
| Idle in transaction | 30 s | [P10.3](10-database.md) |
| Event handler | ack wait (30 s) − 5 s | [P12.9](12-events.md) |
| Job run, reconciler step | the timeout the job declares (required) | [P14](14-background-jobs.md) |
| Connection acquisition | `min(PG_POOL_ACQUIRE_TIMEOUT, remaining)` | [P10.5](10-database.md) |

## Retries, layer by layer

| Layer | Retried | Bound | Source |
|---|---|---|---|
| Database transaction | SQLSTATE `40001`, `40P01` | 3 attempts, `10 ms · 2^n` with jitter | [P10.4](10-database.md) |
| gRPC, idempotent methods | `UNAVAILABLE` | 3 attempts in total (first + 2 retries); retry traffic ≤ 10 % in steady state via `retryThrottling` | [P7.8](07-system-rpc.md) |
| gRPC, other methods | transparent retry only | once | [P7.8](07-system-rpc.md) |
| User-plane HTTP | `GET` on a reset connection | once | [P8.2](08-outbound-http.md) |
| Events | handler errors | `EVENTS_MAX_DELIVER` (8), then dead letters | [P12.7](12-events.md) |
| Queued jobs | handler errors | the worker's maximum attempts, then `dead` | [P14](14-background-jobs.md) |
| Reconcilers | handler errors | the reconciler's maximum, then give up | [P14](14-background-jobs.md) |

## Bulkheads

| Resource | Limit | When reached |
|---|---|---|
| concurrent outbound calls per (member, dependency) | 64 | `RESOURCE_EXHAUSTED` / `OUTBOUND_LIMIT` at once |
| database connections per member | `PG_POOL_MAX` | wait, then `RESOURCE_EXHAUSTED` / `DB_POOL_EXHAUSTED` |
| messages handled at once per subscription | 4; at most 256 unacknowledged per durable | the broker holds back deliveries |

## Notes

- Nested retries multiply: three layers of three attempts make 27 calls at the bottom during an outage, exactly when the dependency can least take them. That is why P9.2 exists.
- Bulkheads and deadlines replace circuit breakers.
