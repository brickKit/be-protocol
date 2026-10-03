[English](07-system-rpc.md) · [中文](07-system-rpc.zh.md)

# P7 System plane: gRPC between components

gRPC is the system protocol between components: what an outbound call carries, what the server enforces, connection reuse, deadlines, retries, bulkheads and batch limits. Every caller on it is a system principal; data filtered by a user's scope is read and written only over REST ([P8](08-outbound-http.md)).

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P7.1 | MUST | gRPC is the system protocol: never routed by the edge, never listed in `edge_routes`. A user request that must read another component's scope-filtered data goes over the user plane ([P8.1](08-outbound-http.md)). Three kinds of rpc are allowed: data with `data_scopes: none` (master data); system protocols (reserve, confirm, cancel; create a task; check a period); completion by ID (`BatchGet`) for IDs the caller already holds | — |
| P7.2 | MUST | Outbound metadata on every call: `traceparent`, `tracestate`, `baggage` (W3C); `x-request-id`; **`be-caller`** = the calling component's ID (in a shell, the calling member's), always; `be-actor-sub` = the platform `sub` of the user whose request led to the call, read from the context **at call time**, absent for background work; `be-actor-act` = the token's `act` chain as JSON when present. An inbound call without `be-caller` answers `UNAUTHENTICATED` with reason `MISSING_CALLER` | CP-RPC-01, CP-RPC-02, CP-OUT-08 |
| P7.3 | MUST | The server marks every call as a system principal `{caller, actor_sub, act}`. `be-caller` and `be-actor-*` are recorded (logs, audit), never used to grant access. A user-facing rpc kept in a contract answers `UNAUTHENTICATED` from the runtime before any component code runs; never `INTERNAL`, never a crash | CP-RPC-03 |
| P7.4 | MUST, order INTERNAL | Server interceptors, unary and streaming alike, in this order: panic recovery → identity → deadline floor (10 s when the caller sent no `grpc-timeout`) → batch limit (P7.10) → error-detail normalisation ([P4.2](04-errors.md)) → RED metrics → tracing | CP-RPC-02 |
| P7.5 | MUST | Server parameters: max receive message size set explicitly to 4 MiB; `MaxConnectionAge` = `GRPC_MAX_CONNECTION_AGE` (default 5 min) with `MaxConnectionAgeGrace` 30 s, which MUST stay longer than the longest deadline the server accepts (the 10 s floor of P7.4, a route's declared deadline), so a `GOAWAY` never cuts an admitted call; keepalive enforcement `MinTime` 20 s, pings without active calls refused, where the server library can enforce it (grpc-js has no such setting: a runtime that cannot enforce it states so in its README and relies on clients keeping P7.6). Each member of a shell has its own server on its own port | CP-RPC-04, CP-RPC-05 |
| P7.6 | MUST | Client connections are reused per (member, dependency, port), created lazily, closed at stop: in steady state one TCP connection per dependency. Keepalive: ping after 30 s idle on an active call, 10 s timeout, no pings without active calls. The address is `<DEP>_GRPC_ENDPOINT` with the scheme stripped ([P2.6](02-configuration.md)), or a slot family's `*_GRPC_URL` read the same way ([P2.10](02-configuration.md)). Nothing about the user is captured when a connection is dialled | CP-OUT-01 |
| P7.7 | MUST | Outbound deadline: `min(3 s, remaining − 50 ms)`. With less than 50 ms remaining the call is not sent and fails with `DEADLINE_EXCEEDED` / `DEADLINE_BUDGET_EXHAUSTED`. A system rpc that legitimately needs longer declares it as a method option (reserved, not defined in 1.0) | CP-OUT-02 |
| P7.8 | MUST | Retries are decided by the contract: a method whose `idempotency_level` is `NO_SIDE_EFFECTS` or `IDEMPOTENT` is retried on `UNAVAILABLE` only: `maxAttempts` 3 in total (the first attempt plus at most 2 retries), backoff 50 ms initial, 500 ms max, multiplier 2. Other methods get only gRPC's transparent retry (a request that never left the client). The retry budget is `retryThrottling {maxTokens: 10, tokenRatio: 0.1}`, and "retry traffic ≤ 10 %" is its steady-state bound, not a hard cap. The scope of the budget follows the gRPC library, and each runtime states it: Go and Python count it per client channel (one per member, dependency and port, P7.6), so one member's retries never spend another's, and refill it when the channel's resolver updates (typically after a `GOAWAY`); grpc-js counts it per process and target and does not refill it on re-resolution, so in a TypeScript shell members calling the same dependency share one budget. Hedging is off. Every rpc whose request has an `idempotency_key` field declares `idempotency_level = IDEMPOTENT` (gate `idempotency-level-scan`) | CP-OUT-03, CP-OUT-04 |
| P7.9 | MUST | Outbound bulkhead: at most 64 concurrent calls per (member, dependency). The 65th fails at once with `RESOURCE_EXHAUSTED` / `OUTBOUND_LIMIT`; calls are never queued | CP-OUT-05 |
| P7.10 | MUST | Batch limit: a repeated field of IDs declares its limit with the field option `(be.v1.max_items) = N` ([`proto/be/v1/limits.proto`](../proto/be/v1/limits.proto)); without it the limit is 500. A larger request answers `INVALID_ARGUMENT` with `ErrorInfo{reason: BATCH_TOO_LARGE, metadata: {field, max, got}}` plus `BadRequest`. Callers split large sets into chunks of at most the limit. Every custom option of the `be.*` packages has a **short name unique across all options a component's protos can see** (some generators, ts-proto among them, expose an option by its short name without its package): `max_items` is taken, and a later option never reuses the short name of any option, ours or another package's. Every official SDK ships the generated code of `be/v1/limits.proto` (Python: an importable `be.v1.limits_pb2`), so a component's generated code links to one copy | CP-RPC-06 |
| P7.11 | MUST | No streaming rpcs. No compression, except that a response above 1 MiB MAY be gzip-compressed per call. Proto packages are named `<domain>.<name>.v<n>` and change only by adding (`buf breaking`) | — |
| P7.12 | MUST | Client interceptors, in this order: default deadline (P7.7) → outbound bulkhead (P7.9) → metadata (P7.2) → client RED metrics → the transaction guard ([P8.4](08-outbound-http.md)) | — (order INTERNAL) |
| P7.13 | MUST | Every method declares `option idempotency_level`: `NO_SIDE_EFFECTS` for reads, `BatchGet` and `GetStatus`; `IDEMPOTENT` for every write that takes an `idempotency_key`. Every aggregate root offers `BatchGet`; every cross-component write offers `GetStatus` by idempotency key ([P13](13-idempotency.md)) | — (gate) |
| P7.14 | MUST | Ports say what they speak in `component.yaml`: the main port `deployment.protocol: http`, the extra port named `grpc` `protocol: grpc` (any other extra port its own protocol, `http`, `grpc` or `tcp`). brickKit writes it as the Kubernetes Service port's `appProtocol` (the deploy file's `k8s.appProtocols` may rename the word for the cluster), so a mesh or gateway that reads it balances gRPC per request instead of per connection; it changes nothing on Docker / Podman and nothing about the injected addresses. `MaxConnectionAge` (P7.5) remains the balancing that works without a mesh | CP-CORE-12 |

## Metadata

| Key | Value | Set by |
|---|---|---|
| `grpc-timeout` | the caller's remaining budget (P7.7) | caller runtime |
| `traceparent`, `tracestate`, `baggage` | W3C trace context | caller runtime |
| `x-request-id` | the inbound request's ID, or a new one | caller runtime |
| `be-caller` | the calling component's or member's ID | caller runtime |
| `be-actor-sub` | the user's platform `sub`, read at call time | caller runtime |
| `be-actor-act` | the `act` chain, JSON | caller runtime |
| `authorization` | reserved for a service token (`sub: svc:<id>`) across a trust boundary | — |

## Service config

The service config every runtime generates for a dependency's retryable methods; the JSON is identical in every language:

```json
{
  "methodConfig": [{
    "name": [{ "service": "erp.inventory.v1.InventoryService", "method": "GetReservationStatus" }],
    "retryPolicy": {
      "maxAttempts": 3,
      "initialBackoff": "0.05s",
      "maxBackoff": "0.5s",
      "backoffMultiplier": 2,
      "retryableStatusCodes": ["UNAVAILABLE"]
    }
  }],
  "retryThrottling": { "maxTokens": 10, "tokenRatio": 0.1 }
}
```

## Notes

- `MaxConnectionAge` is what spreads load on Kubernetes: kube-proxy balances per TCP connection, so a reused HTTP/2 connection would stay on one pod; `GOAWAY` every five minutes lets the client reconnect to a pod chosen afresh.
- Members of one shell call each other over the network exactly as standalone ([P19.2](19-shells.md)); there is no in-process transport.
