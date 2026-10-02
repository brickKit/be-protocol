[English](13-idempotency.md) · [中文](13-idempotency.zh.md)

# P13 Command idempotency

How a write command with an idempotency key is claimed, bound, replayed and expired, over REST and gRPC alike. Table: `besdk_idempotency` ([ddl/](../ddl/)). Fingerprint vectors: `vectors/idempotency/`.

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P13.1 | MUST | Every write command with a side effect accepts an idempotency key ([P3.7](03-http-surface.md) on REST; the request field `idempotency_key` on gRPC). A key lives in a **caller namespace**: `user:<sub>` for a user request, `svc:<be-caller>` for a system call, `system` for the component's own background work | CP-IDEM-01, CP-IDEM-06 |
| P13.2 | MUST | A key is bound to three things: `command` (the permission key, or the rpc's full name), `target` (the aggregate ID the command acts on; empty for a create) and `request_hash` (SHA-256 of the fingerprint fields declared for the command, canonicalised with RFC 8785 JCS). Same caller and same key with a different command, target or hash answers `400` / `INVALID_ARGUMENT` with reason `IDEMPOTENCY_MISMATCH` | CP-IDEM-02, CP-IDEM-03, CP-IDEM-04 |
| P13.3 | MUST | A key claimed but not completed (a two-step command: claim, a network call, then complete) answers `409` / `ABORTED` with reason `IDEMPOTENCY_IN_PROGRESS`. A completed key replays the stored result with the same status code, without executing again. A step that fails for certain releases the claim, so the same key may be retried | CP-IDEM-01, CP-IDEM-05 |
| P13.4 | MUST | Different callers using the same key are independent: neither sees the other's result, and nothing in any answer reveals that the key exists in another namespace | CP-IDEM-06 |
| P13.5 | MUST | The order of checks is fixed: validate arguments → authorize the target and the data scope → look up or claim the key → check the state machine → write. A replayed create is read back through the component's own scoped read; out of scope answers like a mismatch | CP-IDEM-02 |
| P13.6 | MUST | Concurrent requests with the same caller and key execute once; the others receive the replayed result or `IDEMPOTENCY_IN_PROGRESS`. The claim is atomic ([P10.9](10-database.md)) | CP-IDEM-07 |
| P13.7 | MUST | A key is valid for **30 days** from its first use (`expires_at = created_at + 30 days`); after that the same key is a new command. The runtime deletes expired rows. Every command contract with a key states the 30 days | — |
| P13.8 | MUST | An event handler that issues another component's write command uses a key derived deterministically from the event (`crm-won:<opportunity_id>`), in the `svc:` namespace, so a redelivery is a retry of the same command | — |
| P13.9 | MUST | Every callee of a cross-component write offers `GetStatus` by idempotency key; after a timeout the caller asks before it compensates | — |

## Fingerprint

1. Take the request fields the command declares as its fingerprint (the business fields; never the key itself, never transport headers).
2. Serialise them as one JSON object and canonicalise with RFC 8785 (JCS).
3. `request_hash` = SHA-256 of the UTF-8 bytes; stored as 32 raw bytes (`BYTEA`).

## Claim statement

```sql
-- a new claim returns its status; a key that is already taken returns no row
INSERT INTO besdk_idempotency (caller, idempotency_key, command, target, request_hash, status, expires_at)
VALUES ($1, $2, $3, $4, $5, 'CLAIMED', now() + interval '30 days')
ON CONFLICT (caller, idempotency_key) DO NOTHING
RETURNING status;
-- no row returned → SELECT command, target, request_hash, status, result … FOR UPDATE, then:
--   any of command/target/request_hash differs → IDEMPOTENCY_MISMATCH
--   status = 'CLAIMED' → IDEMPOTENCY_IN_PROGRESS
--   status = 'DONE'    → replay result
```

## Notes

- Namespacing by caller means another caller's key is, for me, simply unused: I cannot read its result or take over a key the system derives.
- A one-step command claims, executes and completes in one transaction; only a two-step command keeps `CLAIMED` across a network call.
