[English](05-identity.md) · [中文](05-identity.zh.md)

# P5 身份：验证 access token

组件怎么在本地、用身份 provider 公布的公钥验证平台的 access token，要求并读取哪些 claim，以及 stale token 怎么回答。签发 token、登录和 token 交换属于身份族契约（`brickKit/contract-infra-iam`，major `iam/1`）。Claim schema：[`access-token.schema.json`](../schemas/access-token.schema.json)。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P5.1 | MUST | token 以 `Authorization: Bearer <jwt>` 传递。请求头缺失、用了别的 scheme，或值不是 compact JWS，答 `401` `TOKEN_INVALID` | CP-AUTH-01 |
| P5.2 | MUST | `alg` 只接受白名单 `RS256`、`ES256`、`EdDSA` 里的值，而且必须等于按 `kid` 选出的那把 JWKS 钥匙的 `alg`；token 头不能选择它。`kid` 必填。`alg: none`、任何 HMAC 算法和缺失 `kid`，都答 `401` `TOKEN_INVALID` | CP-AUTH-02 |
| P5.3 | MUST | 必需的 claim：`iss` 等于 `IAM_ISSUER`；`aud`（字符串或数组）包含 `TENANT_ID`；`typ` 等于 `"access"`，`"refresh"` 和缺失的 `typ` 都拒收；`sub` 非空；`exp`、`iat` 和 `jti` 都存在；`nbf` 存在时检查。`exp`、`nbf` 和 `iat` 的时钟偏差容忍 60 s。任何一项失败都答 `401` `TOKEN_INVALID` | CP-AUTH-03, CP-AUTH-04, CP-AUTH-05, CP-AUTH-06 |
| P5.4 | MUST | JWKS 来自 `{IAM_URL}/.well-known/jwks.json`（路径由身份族固定，[P2.10](02-configuration.zh.md)）：本地缓存最长 1 h；遇到不认识的 `kid` 触发一次重新拉取，最多每 30 s 一次，之后判失败；每次拉取 3 s 超时；拉取失败沿用已有的钥匙（fail-static）。钥匙轮换期间，用当前钥匙和上一把钥匙签的 token 都能验过 | CP-AUTH-07 |
| P5.5 | MUST | 组件读取的 claim：`sub`、`tenant_id`、`roles[]`、`dept_path`、`act{sub, kind, act}`、`ceil[]`、`dg`、`azp`、`locale`。`org_id` 已弃用：会读，但从不用于判定。`act.kind` 取 `user`、`agent`、`svc` 之一。bundle 的能力 `agents` 为 `false` 时，`act` 链里含 `kind: agent` 的 token 答 `401` `UNSUPPORTED_DELEGATION`；能力 `delegation` 为 `false` 时，带 `ceil` 或 `dg` 的 token 同样如此 | CP-AUTH-12 |
| P5.6 | MUST | stale token：bundle 里有 `stale_since[sub]`，且 token 的 `iat` 早于 `stale_since[sub]` 减 5 s 时，请求答 `401`，reason 为 `TOKEN_STALE`，带响应头 `WWW-Authenticate: Bearer error="token_stale"`。前端刷新一次后重试 | CP-AUTH-08 |
| P5.7 | MUST | 服务账号的 `sub` 形如 `svc:<id>`；它带角色，判定方式与用户完全相同。目前还没有签发方签发这种 token；组件必须接受这种形式 | — |
| P5.8 | INTERNAL | 原始 token 只存在请求上下文的一个私有槽里，供用户面 HTTP 转发（[P8.1](08-outbound-http.zh.md)）。它永不放进用户对象，永不进日志，永不发给第三方 | — |
| P5.9 | MUST | 不认识的 claim 忽略。JSON 类型不对的 claim（例如 `roles` 不是字符串数组）答 `401` `TOKEN_INVALID` | CP-AUTH-03 |

## claim 清单

| Claim | 类型 | 必填 | 含义 |
|---|---|---|---|
| `iss` | string | 是 | 平台签发方，`IAM_ISSUER` |
| `aud` | string 或 string 数组 | 是 | 包含本部署，`TENANT_ID` |
| `sub` | string | 是 | 平台用户 ID（UUIDv7，对组件不透明），或 `svc:<id>` |
| `typ` | `"access"` | 是 | 组件永不接受 `"refresh"` token |
| `iat`、`exp` | integer（秒） | 是 | access TTL 为 600 s |
| `nbf` | integer（秒） | 否 | 存在时检查 |
| `jti` | string | 是 | token ID |
| `tenant_id` | string | 否 | 租户 |
| `roles` | string 数组 | 否（空 = 没有角色） | 角色代码，由授权 provider 在登录和刷新时解析 |
| `dept_path` | string | 否 | 用户的部门路径，`/<id>/<id>/…/`；为空或缺失 = 没有部门（[P6.4](06-authorization.zh.md)） |
| `act` | object `{sub, kind, act?}` | 否 | 行事方，可以嵌套（RFC 8693 §4.1） |
| `ceil` | string 数组 | 否 | 委托链上的天花板 profile 代码 |
| `dg` | string | 否 | 委托授予 ID |
| `azp` | string | 否 | 客户端（`pc`、`mobile`……） |
| `locale` | string（BCP 47） | 否 | 用户的语言，只用于服务端渲染的文本 |
| `org_id` | string | 否 | 已弃用 |

## 说明

- 授权判定本身见 [P6](06-authorization.zh.md)；token 从不携带权限键。
- 身份 provider 在 JWKS 里同时公布当前和上一把签名钥匙，所以轮换不需要和组件协调。
