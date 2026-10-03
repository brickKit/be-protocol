[English](05-identity.md) · [中文](05-identity.zh.md)

# P5 Identity: verifying access tokens

How a component verifies the platform's access token locally against the identity provider's published keys, which claims it requires and reads, and how a stale token is answered. Issuing tokens, login and token exchange belong to the identity family contract (`brickKit/contract-infra-iam`, major `iam/1`). Claims schema: [`access-token.schema.json`](../schemas/access-token.schema.json).

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P5.1 | MUST | The token travels as `Authorization: Bearer <jwt>`. A missing header, another scheme, or a value that is not a compact JWS answers `401` `TOKEN_INVALID` | CP-AUTH-01 |
| P5.2 | MUST | `alg` is accepted only from the allow-list `RS256`, `ES256`, `EdDSA`, and MUST equal the `alg` of the JWKS key selected by `kid`; the token header cannot choose it. `kid` is required. `alg: none`, any HMAC algorithm and a missing `kid` answer `401` `TOKEN_INVALID` | CP-AUTH-02 |
| P5.3 | MUST | Required claims: `iss` equals `IAM_ISSUER`; `aud` (string or array) contains `TENANT_ID`; `typ` equals `"access"`, while `"refresh"` and a missing `typ` are refused; `sub` is non-empty; `exp`, `iat` and `jti` are present; `nbf` is checked when present. Clock skew tolerance is 60 s for `exp`, `nbf` and `iat`. Any failure answers `401` `TOKEN_INVALID` | CP-AUTH-03, CP-AUTH-04, CP-AUTH-05, CP-AUTH-06 |
| P5.4 | MUST | JWKS from `{IAM_URL}/.well-known/jwks.json` (the identity family fixes the path, [P2.10](02-configuration.md)): cached locally for at most 1 h; an unknown `kid` triggers one refetch, at most once per 30 s, then fails; each fetch times out after 3 s; a failed fetch keeps the keys already held (fail-static). During a key rotation, tokens signed with the current and the previous key both verify | CP-AUTH-07 |
| P5.5 | MUST | The claims a component reads: `sub`, `tenant_id`, `roles[]`, `dept_path`, `act{sub, kind, act}`, `ceil[]`, `dg`, `azp`, `locale`. `org_id` is deprecated: read, never used for a decision. `act.kind` is one of `user`, `agent`, `svc`. When the bundle's capability `agents` is `false`, a token whose `act` chain contains `kind: agent` answers `401` `UNSUPPORTED_DELEGATION`; likewise a token carrying `ceil` or `dg` when the capability `delegation` is `false` | CP-AUTH-12 |
| P5.6 | MUST | Stale tokens: when the bundle's `stale_since[sub]` exists and the token's `iat` is earlier than `stale_since[sub]` minus 5 s, the request answers `401` with reason `TOKEN_STALE` and the header `WWW-Authenticate: Bearer error="token_stale"`. The frontend refreshes once and retries | CP-AUTH-08 |
| P5.7 | MUST | A service account's `sub` has the form `svc:<id>`; it carries roles and is decided exactly like a user. No issuer issues such tokens yet; components MUST accept the form | — |
| P5.8 | INTERNAL | The raw token is kept only in a private slot of the request context, for forwarding by user-plane HTTP ([P8.1](08-outbound-http.md)). It is never placed in the user object, never logged, never sent to a third party | — |
| P5.9 | MUST | Unknown claims are ignored. A claim with the wrong JSON type (for example `roles` not an array of strings) answers `401` `TOKEN_INVALID` | CP-AUTH-03 |

## Claims

| Claim | Type | Required | Meaning |
|---|---|---|---|
| `iss` | string | yes | the platform issuer, `IAM_ISSUER` |
| `aud` | string or array of strings | yes | contains the deployment, `TENANT_ID` |
| `sub` | string | yes | the platform user id (UUIDv7, opaque to components), or `svc:<id>` |
| `typ` | `"access"` | yes | `"refresh"` tokens are never accepted by a component |
| `iat`, `exp` | integer (seconds) | yes | access TTL is 600 s |
| `nbf` | integer (seconds) | no | checked when present |
| `jti` | string | yes | token id |
| `tenant_id` | string | no | the tenant |
| `roles` | array of strings | no (empty = no roles) | role codes, resolved by the authorization provider at login and refresh |
| `dept_path` | string | no | the user's department path, `/<id>/<id>/…/`; empty or absent = no department ([P6.4](06-authorization.md)) |
| `act` | object `{sub, kind, act?}` | no | the acting party, nestable (RFC 8693 §4.1) |
| `ceil` | array of strings | no | ceiling profile codes on a delegation chain |
| `dg` | string | no | delegation grant id |
| `azp` | string | no | the client (`pc`, `mobile`, …) |
| `locale` | string (BCP 47) | no | the user's language, for server-rendered text only |
| `org_id` | string | no | deprecated |

## Notes

- The authorization decision itself is in [P6](06-authorization.md); a token never carries permission keys.
- The identity provider publishes the current and the previous signing key in its JWKS, so rotation needs no coordination with components.
