[English](README.md) · [中文](README.zh.md)

# Vectors: idempotency

The request fingerprint, the decision taken when a key is seen again, where the key comes from, and the caller namespace (protocol P3.7, P13; foundations 11). SDK API: Go `besdk.Idempotent` / `Command`, and the same in Python and TypeScript; the fingerprint function is internal but must be exposed to the SDK's own tests.

## Files

| File | Cases | Operations |
|---|---|---|
| `fingerprint.json` | 76 | `fingerprint` |
| `decide.json` | 13 | `decide` |
| `keys.json` | 12 | `resolve_key`, `caller_namespace`, `expires_at` |

## Operations

| Op | Input | Expected |
|---|---|---|
| `fingerprint` | `json_text`: the fingerprint object as raw JSON text, parsed by the SDK's own JSON parser | `canonical`: the RFC 8785 (JCS) text; `sha256`: lower-case hex of SHA-256 over its UTF-8 bytes (the `request_hash` column) |
| `decide` | `rows`: the caller's `besdk_idempotency` rows; `now`; `incoming`: `caller` (`{kind: user, sub}`, `{kind: system_call, be_caller}`, `{kind: background}`), `key`, `command`, `target`, `request` (JSON text) | `caller` (the namespace) and `outcome`: `EXECUTE` (claim and run), `REPLAY` (with the stored `result`), or `REJECT` with `code`, `http`, `reason` |
| `resolve_key` | `header` (`Idempotency-Key`), `body` (`idempotency_key`), either may be `null` | `key` (or `null`: no idempotency) |
| `caller_namespace` | `caller` | `caller`: `user:<sub>`, `svc:<be-caller>` or `system` |
| `expires_at` | `created_at` | `expires_at` = created_at + 30 days (720 h) |

## Rules

- **JSON input is I-JSON** (RFC 7493): duplicate member names, `NaN`, `Infinity`, numbers that overflow a double, and any non-JSON text are `JSON_INVALID`.
- **Every number is an IEEE 754 double** and is written the ECMAScript way (RFC 8785 §3.2.2.3): `1.0`, `1E0`, `100e-2` are all `1`; `-0` is `0`; `1e21` and above, and below `1e-6`, use the exponent form; an integer beyond 2^53 collapses to the nearest double. A Python implementation must not keep exact big integers.
- **Strings are not normalised**: NFC and NFD forms of one word give different hashes. Escapes: `\"`, `\\`, `\b \t \n \f \r`, other controls as `\u00xx` in lower case; everything else, U+007F, U+2028 and U+2029 included, is raw UTF-8.
- **Members are sorted by UTF-16 code units**, not code points: U+1F600 (`😀`) sorts before U+FFFF.
- **The fingerprint object never contains the idempotency key itself**; it holds the business fields the command declares.
- **Decision order**: no row for (caller, key), or `now ≥ expires_at` → `EXECUTE`; then a different `command`, `target` or `request_hash` → `INVALID_ARGUMENT` / 400 / `IDEMPOTENCY_MISMATCH` (checked before the state, so a mismatching retry of an in-flight claim is a mismatch); then `CLAIMED` → `ABORTED` / 409 / `IDEMPOTENCY_IN_PROGRESS`; otherwise `REPLAY`.
- **Namespaces never meet**: another user's, a service's or the system's row with the same key is invisible; the outcome is `EXECUTE` and nothing reveals that the key exists elsewhere.
- **Header and body**: equal or only one present → that key; both present and different → 400 `IDEMPOTENCY_MISMATCH`.

## Errors

| Class | Wire |
|---|---|
| `JSON_INVALID` | `INVALID_ARGUMENT` (the request body is not acceptable JSON) |
| `IDEMPOTENCY_MISMATCH` | 400 / `INVALID_ARGUMENT`, platform reason |
| `IDEMPOTENCY_IN_PROGRESS` | 409 / `ABORTED`, platform reason (inside `decide`'s `REJECT`) |

## Decided here

For review: duplicate JSON member names are rejected rather than "last wins"; a mismatch is reported before "in progress"; expiry is a half-open bound (`now == expires_at` is already new); `svc:` and `system` namespaces are as in P13.1, and a service-account token (`sub: svc:…`, P5.7) is out of scope until an issuer exists. The key's own format (length, characters) is not pinned by the protocol and has no vectors yet.

## Regenerate

`python3 gen/gen_idempotency.py`; cross-check with Node and the npm package `canonicalize` (`make xcheck` in [..](../README.md)). The generator asserts the RFC 8785 sample tables (§3.2.2.3 numbers, §3.2.3 sorting, §3.2.4 example) before writing.
