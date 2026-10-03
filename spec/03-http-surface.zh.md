[English](03-http-surface.md) · [中文](03-http-surface.zh.md)

# P3 HTTP 面

组件在主端口上服务什么：三类路径、每次交互都带的请求头和响应头、截止时间、服务端超时、请求体上限、幂等键、分页和版本化。错误见 [P4](04-errors.zh.md)，授权见 [P6](06-authorization.zh.md)。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P3.1 | MUST | 主端口服务三类路径，此外没有别的：**用户面** `/{domain}/{name}/…`（经边缘路由，在 `edge_routes` 里声明）；**运维** `/healthz`、`/readyz`、`/metrics`、`/_be/info`（永不经边缘路由）；**资源契约** `/{domain}/{name}/_authz/*`、`/{domain}/{name}/_shares/*`、`/{domain}/{name}/_lifecycle/*`、`/{domain}/{name}/_ops/*`（经边缘路由，[P6.10](06-authorization.zh.md)、[P16.4](16-data-lifecycle.zh.md)、[P14.4](14-background-jobs.zh.md)）。移动端 BFF 是唯一的例外：它的用户面是 `/graphql` | CP-CORE-11 |
| P3.2 | MUST | 请求 ID：入站带了 `X-Request-Id` 就沿用（客户端伪造的那一份由边缘剥掉）；没带就用 trace ID。每个响应都带 `X-Request-Id`；每个出站调用都带上它（[P7.2](07-system-rpc.zh.md)、[P8.1](08-outbound-http.zh.md)） | CP-CORE-10 |
| P3.3 | MUST | trace：提取入站的 W3C `traceparent`、`tracestate` 和 `baggage`；请求的服务端 span 是调用方 span 的子 span（[P18.1](18-observability.zh.md)） | CP-OBS-01 |
| P3.4 | MUST | 每个路由都有截止时间：取 `HTTP_DEFAULT_TIMEOUT`（默认 10 s），除非路由自己声明了（P3.13）；编排类路由声明 15 s；导出是异步的，永不占住一个同步路由。截止时间一到，取消该请求的下游调用和未结束的事务，组件答 `504`，code 为 `DEADLINE_EXCEEDED`；reason 的取法：取消了一条数据库语句时是 `STATEMENT_TIMEOUT`，依赖带 `ErrorInfo` 回答了 `DEADLINE_EXCEEDED` 时用下游自己的 reason，其它情况是 `DEADLINE_BUDGET_EXHAUSTED` | CP-OUT-07, CP-DB-02 |
| P3.5 | MUST | 服务端超时：读请求头 5 s；读整个请求 30 s；写响应 = 路由截止时间 + 5 s；空闲 keep-alive 连接 120 s。慢速发送请求头的客户端被断开；请求头超时的检查粒度不超过 1 s，所以 6 s 之内一定断开。路由的处理函数受它的截止时间约束（P3.4）：跑过了就答 `504` `DEADLINE_EXCEEDED`，绝不是直接断开连接 | CP-CORE-08 |
| P3.6 | MUST | 请求体上限 1 MiB，除非路由声明了更大。超过的答 `413`，reason 为 `BODY_TOO_LARGE`。文件永不经组件的请求体传输：上传用对象存储的预签名 URL（[P17](17-object-storage.zh.md)） | CP-CORE-09 |
| P3.7 | MUST | 写命令接受的幂等键，可以放在请求头 `Idempotency-Key` 里，也可以放在 body 字段 `idempotency_key` 里；两者等价。两者同时出现且取值不同，答 `400`，reason 为 `IDEMPOTENCY_MISMATCH`（[P13](13-idempotency.zh.md)） | CP-IDEM-08 |
| P3.8 | MUST | 列表按游标分页（AIP-158）：请求参数 `page_size` 和 `cursor`；响应字段 `next_cursor`，到末尾为空。`page_size` 默认 50；超过端点的上限（最多 500）就降到上限，从不拒绝。游标不透明：里面编码了排序键、最后一个 ID 和过滤条件的哈希；带着不同过滤条件发来的游标答 `400` `CURSOR_INVALID`。没有 `offset`，没有精确总数。默认顺序 `created_at DESC, id DESC` | — |
| P3.9 | SHOULD | 由其它组件事件派生的视图（投影、快照、ACL），其 `List` 和 `Get` 带 `X-Data-As-Of`：该视图最近应用过的事件的 `occurred_at`，RFC 3339 | — |
| P3.10 | MUST | 每个请求一行访问日志，`msg` = `http_request`，字段见 [P18.2](18-observability.zh.md) | CP-OBS-02 |
| P3.11 | MUST | 组件里不处理 CORS：默认同源，跨源策略归边缘 | — |
| P3.12 | MUST | `/metrics` 服务 Prometheus 文本格式（[P18.3](18-observability.zh.md)）；`/_be/info` 服务自描述（[P20](20-self-description-and-versioning.zh.md)） | CP-OBS-03, CP-CORE-11 |
| P3.13 | MUST | 路由自己的截止时间和请求体上限，在它的 OpenAPI operation 上声明为 `x-be-deadline-seconds`（整数）和 `x-be-max-body-bytes`（整数），这样边缘、服务端和前端读的是同一个数字。没写就是 P3.4 和 P3.6 的默认值 | — |
| P3.14 | MUST | 在一个 major 版本内，组件的 operation 只增不减。破坏性变更在 `/{domain}/{name}/v2/…` 下发布新的 operation，与旧的并存；旧 operation 在下线日期之前，回答时带 `Deprecation`、`Sunset` 和 `Link: <…>; rel="successor-version"` | — |
| P3.15 | MUST | 访问相关的状态码遵循 [P6.6](06-authorization.zh.md)：token 缺失、无效或 stale 答 `401`；只有记录看得见、但动作不被允许时才答 `403`；记录不存在**或看不见**时答 `404`，读和命令都一样 | CP-SCOPE-07, CP-SCOPE-08 |

## 请求头

| 头 | 含义 |
|---|---|
| `Authorization: Bearer <token>` | 用户的 access token（[P5](05-identity.zh.md)） |
| `Idempotency-Key` | 用于写操作；两者都出现时等于 body 的 `idempotency_key`（[P13](13-idempotency.zh.md)） |
| `X-Request-Id` | 可选；没有就生成 |
| `traceparent`、`tracestate`、`baggage` | W3C trace 上下文，通常在边缘创建 |
| `X-Authz-Revision` | 授权一致性令牌（[P6.11](06-authorization.zh.md)） |

`Accept-Language` 不用于选择错误文案（[P4](04-errors.zh.md)）。

## 响应头

| 头 | 何时 |
|---|---|
| `X-Request-Id` | 总是 |
| `Content-Type: application/problem+json` | 每个 4xx 和 5xx（[P4.1](04-errors.zh.md)） |
| `X-Data-As-Of` | 读派生视图时（P3.9） |
| `Retry-After` | 随 `429` 和 `503`，当错误带有重试延迟时（gRPC `RetryInfo`） |
| `X-Authz-Consistency: stale` | 一个用落后于所请求 revision 的投影过滤出来的列表（[P6.11](06-authorization.zh.md)） |
| `X-Authz-Degraded: graph` | 一个因 provider 缺 `graph` 能力而跳过了图分支的列表（[P6](06-authorization.zh.md)） |
| `WWW-Authenticate: Bearer error="token_stale"` | `401 TOKEN_STALE`（[P5.6](05-identity.zh.md)） |
| `Deprecation`、`Sunset`、`Link` | 计划下线的 operation（P3.14） |

## 列表形状

```json
{ "items": [ … ], "next_cursor": "eyJr…" }
```

数组的字段名由契约定（`items`、`orders`……）；`next_cursor` 是固定的。资源列表的行在适用时带 `_access`（[P6.9](06-authorization.zh.md)）和 `_masked`（[P6.8](06-authorization.zh.md)）。

## 说明

- P3.4 的截止时间是预算的根，下面每一层都在它的基础上缩短（[P9](09-deadlines-and-retries.zh.md)）。
- 超过上限的 `page_size` 被降到上限而不是被拒绝，这样按更大上限写的客户端仍然能用。
- 边缘按路径段为界匹配用户面前缀：`/erp/sales` 接 `/erp/sales` 和 `/erp/sales/…`，从不接 `/erp/salesman`。be-ops 在两种目标上都从 `edge_routes`（P3.1）生成路由：Kubernetes 的部署条目写 `paths`，brickKit 把它变成以路径段为界的 Ingress 前缀（几个组件共用一个主机名时，各自要写同一个 `tlsSecret`）；Docker / Podman 的部署条目写 Traefik 标签，用 `PathRegexp`（`^/erp/sales(/|$)`），从不用按字符串匹配的 `PathPrefix`。Traefik（≥ 3.2）接在部署文件 `network:` 指定的项目网络上。
