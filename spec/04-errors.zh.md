[English](04-errors.md) · [中文](04-errors.zh.md)

# P4 错误

REST、gRPC 和 GraphQL 共用一个错误对象：RFC 9457 problem details，承载 Google AIP-193 `ErrorInfo` 的成员（`reason`、`domain`、`metadata`）；每个组件一份 reason 目录；外加 domain `be` 的保留 reason。Schema：[`problem.schema.json`](../schemas/problem.schema.json)、[`errors-yaml.schema.json`](../schemas/errors-yaml.schema.json)；目录：[`errors-be.yaml`](../schemas/errors-be.yaml)。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P4.1 | MUST | 组件的每个 `4xx` 和 `5xx` REST 响应都带 `Content-Type: application/problem+json`，body 是下面的形状。`reason` 是 `UPPER_SNAKE`。`domain` 是原样不变的组件 ID（`erp/inventory`），保留 reason 则是 `be`；槽位族的成员用族的 ID 代替自己的 ID（每个授权成员都答 `domain: infra/authz`），这样前端每个族只需一张表。`type` 是 `urn:be:<domain>:<reason>`。没有 `error` 字段，也没有 `retry_after_ms` 字段：重试延迟只经 `Retry-After` 响应头传递 | CP-ERR-01 |
| P4.2 | MUST | 在 gRPC 上，错误是一个标准状态码，以默认语言的 `detail` 作为它的 message，总是附带 `google.rpc.ErrorInfo{reason, domain, metadata}`，适用时再附 `BadRequest`、`PreconditionFailure`、`RetryInfo`、`ResourceInfo`。REST 与 gRPC 按下表双向映射，所以一个经 gRPC 调别的组件、经 REST 回答自己用户的组件不会丢任何信息。不使用 `LocalizedMessage` | CP-ERR-02 |
| P4.3 | MUST | `INTERNAL`、`UNKNOWN` 和 `DATA_LOSS` 一律回答 `reason: INTERNAL`、`domain: be`、一句通用的 `detail` 和 `trace_id`。原始错误（SQL 文本、栈、token 解析器的报错）只进日志。组件代码无法选择不这样做 | CP-ERR-03 |
| P4.4 | MUST | 每个组件在 `contracts/errors.yaml` 里列出自己的 reason（[格式](../schemas/errors-yaml.schema.json)）：`{reason, code, http, params[], title{zh,en}, message{zh,en}, since, deprecated}`。条目只增不改：永不改名、删除或复用；用 `deprecated: true` 退役。组件在自己 domain 里抛的每个 reason 都列在这里（槽位族成员的 reason 列在它族契约的 `errors.yaml` 里）；domain `be` 的 reason 列在 `errors-be.yaml`；从依赖转发来的 reason 保留该依赖的 `domain`，列在该依赖的目录里（P4.9）。前端按目录翻译；服务端不翻译 | CP-ERR-04 |
| P4.5 | MUST | GraphQL（移动端 BFF）：`errors[].extensions = {code, reason, domain, metadata, request_id, trace_id}`，从下游错误复制而来 | CP-ERR-01 |
| P4.6 | MUST | 运行时按错误的 code 决定日志级别：`INTERNAL`、`UNKNOWN`、`DATA_LOSS` → ERROR；`UNAVAILABLE`、`DEADLINE_EXCEEDED` → WARN；`CANCELLED`，包括停机时的取消 → 不记；所有调用方错误（`INVALID_ARGUMENT`、`NOT_FOUND`、`PERMISSION_DENIED`、`FAILED_PRECONDITION`、`UNAUTHENTICATED`……）→ INFO | CP-OBS-02 |
| P4.7 | MUST | 组件永不在自己的 domain 里抛保留的 reason 名，也永不抛不在 `errors-be.yaml` 里的 domain `be` 的 reason | CP-ERR-04 |
| P4.8 | MUST | `metadata` 的值只能是字符串（数字和日期由产生方格式化）；永不放密钥，除调用方自己发来的内容之外永不放个人数据 | CP-ERR-01 |
| P4.9 | SHOULD | 转发依赖的错误：当它的 `reason` 和 `domain` 对用户有意义时（库存不足），保留它们；只有映射成自己的 reason 能增加含义时才映射 | — |

## 错误体

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

| 字段 | 必填 | 规则 |
|---|---|---|
| `type` | 是 | `urn:be:<domain>:<reason>` |
| `title` | 是 | 该 reason 在部署默认语言（`DEFAULT_LOCALE`）下的简短标题，取自目录 |
| `status` | 是 | HTTP 状态码 |
| `code` | 是 | gRPC 规范 code 名 |
| `reason`、`domain` | 是 | 错误的身份；前端按 `domain` + `reason` 查找 |
| `detail` | 是 | 用 `DEFAULT_LOCALE` 渲染好的消息；`INTERNAL` 时是通用文案 |
| `metadata` | 是（可以是 `{}`） | 字符串值，即目录模板的参数 |
| `violations` | 否 | 字段错误，来自 gRPC `BadRequest` |
| `instance` | 是 | 请求路径 |
| `request_id`、`trace_id` | 是 | 总是存在 |

## 状态码映射

| gRPC code | HTTP | gRPC code | HTTP |
|---|---|---|---|
| `INVALID_ARGUMENT`、`FAILED_PRECONDITION`、`OUT_OF_RANGE` | 400 | `RESOURCE_EXHAUSTED` | 429 |
| `UNAUTHENTICATED` | 401 | `CANCELLED` | 499 |
| `PERMISSION_DENIED` | 403 | `UNIMPLEMENTED` | 501 |
| `NOT_FOUND` | 404 | `UNAVAILABLE` | 503 |
| `ALREADY_EXISTS`、`ABORTED` | 409 | `DEADLINE_EXCEEDED` | 504 |
| `INTERNAL`、`UNKNOWN`、`DATA_LOSS` | 500 | | |

一个例外：reason `BODY_TOO_LARGE`（code `INVALID_ARGUMENT`）回答 HTTP `413`。`RetryInfo` 变成 `Retry-After`（整秒，向上取整），反向亦然。

## 保留 reason（domain `be`）

这是完整集合；[`errors-be.yaml`](../schemas/errors-be.yaml) 里是同样的这些行，带两种语言的标题和消息。

| Reason | Code | 什么时候抛 |
|---|---|---|
| `INTERNAL` | `INTERNAL` | 任何内部错误，原始错误被隐藏 |
| `TOKEN_STALE` | `UNAUTHENTICATED` | token 早于一次角色变更 |
| `MISSING_PERMISSION` | `PERMISSION_DENIED` | 调用方缺少某个权限键 |
| `NOT_FOUND` | `NOT_FOUND` | 记录不存在或不可见 |
| `AUTHZ_NOT_READY` | `UNAVAILABLE` | 权限 bundle 还没加载 |
| `NOT_READY` | `UNAVAILABLE` | 进程还没就绪：还没有 bundle、数据库身份探测没通过，或迁移落后于镜像（`/readyz`） |
| `TOKEN_INVALID` | `UNAUTHENTICATED` | 没有 token，或 token 校验不过（签名、`iss`、`aud`、`typ`、过期） |
| `UNSUPPORTED_DELEGATION` | `UNAUTHENTICATED` | token 经由一种 provider 不支持的代理方行事 |
| `MISSING_CALLER` | `UNAUTHENTICATED` | 系统面调用没带 `be-caller` |
| `OUT_OF_SCOPE` | `PERMISSION_DENIED` | 请求参数本身就是一个范围取值，且不在调用方的范围内（`warehouse_id=7`）；或者一条看得见的记录，不在调用方所持动作键的范围内 |
| `FIELD_FORBIDDEN` | `PERMISSION_DENIED` | 写了一个调用方看不到的字段 |
| `SORT_FORBIDDEN` | `INVALID_ARGUMENT` | 按对调用方掩码的字段排序、过滤或聚合 |
| `SHARE_NOT_ALLOWED` | `PERMISSION_DENIED` | 这个资源类型或这个调用方不允许做的分享 |
| `CAPABILITY_UNAVAILABLE` | `UNIMPLEMENTED` | 安装的 provider 或适配器缺某项能力；`metadata.capability` 写明是哪项 |
| `IDEMPOTENCY_MISMATCH` | `INVALID_ARGUMENT` | 一个键被复用在别的命令、目标或请求体上 |
| `IDEMPOTENCY_IN_PROGRESS` | `ABORTED` | 这个键的第一次使用还没结束 |
| `CURSOR_INVALID` | `INVALID_ARGUMENT` | 游标与请求不匹配 |
| `BATCH_TOO_LARGE` | `INVALID_ARGUMENT` | ID 数超过一个批次允许的数量 |
| `LOCK_TIMEOUT` | `ABORTED` | 锁等待超过了 `lock_timeout` |
| `STATEMENT_TIMEOUT` | `DEADLINE_EXCEEDED` | 一条语句或一个事务超过了它的超时 |
| `TX_CONFLICT` | `ABORTED` | 自动重试之后序列化失败仍然存在 |
| `DB_POOL_EXHAUSTED` | `RESOURCE_EXHAUSTED` | 成员的连接预算一直满到它的截止时间 |
| `OUTBOUND_LIMIT` | `RESOURCE_EXHAUSTED` | 对同一个依赖的并发调用太多 |
| `DEADLINE_BUDGET_EXHAUSTED` | `DEADLINE_EXCEEDED` | 剩余时间太少，不足以发起调用 |
| `BODY_TOO_LARGE` | `INVALID_ARGUMENT` | 请求体超过路由的上限；以 HTTP 413 回答 |
| `RANGE_COLD` | `FAILED_PRECONDITION` | 请求的时间范围已转入冷存储；`metadata` 给出冷区间，以及能否解冻、能否导出 |
| `UNIT_SEALED` | `FAILED_PRECONDITION` | 修改一个已封存的生命周期单元；用一张新的冲销单据来更正 |
| `RATE_LIMITED` | `RESOURCE_EXHAUSTED` | 达到了边缘对该调用方或该路由的限流；HTTP 429，带 `Retry-After` |
| `UPSTREAM_UNAVAILABLE` | `UNAVAILABLE` | 边缘连不上组件；HTTP 502 或 503（目录里的 `http_also`） |
| `UPSTREAM_TIMEOUT` | `DEADLINE_EXCEEDED` | 组件没在边缘的截止时间内回答；HTTP 504 |
| `NETWORK_IN_TX` | `INTERNAL` | 工作单元持有未结束的事务时发起了出站调用（gRPC、用户面或第三方 HTTP、直接发布，[P8.4](08-outbound-http.zh.md)）；编程错误 |
| `DB_TOO_MANY_CONNECTIONS` | `UNAVAILABLE` | PostgreSQL 拒绝新连接，SQLSTATE `53300`（[P10.4](10-database.zh.md)）；HTTP 503 |
| `NESTED_TX` | `INTERNAL` | 同一个工作单元已经持有一个事务时又打开了一个（[P10.6](10-database.zh.md)）；编程错误 |

`RATE_LIMITED`、`UPSTREAM_UNAVAILABLE`、`UPSTREAM_TIMEOUT` 由边缘抛出，组件永不抛出：边缘自己产生的回答（404、413、429、502、503、504）带这个错误体，`domain: be`。

黑盒永远看不到的内部守卫失败（嵌套事务，`NESTED_TX`，[P10.6](10-database.zh.md)；事务内的网络调用，`NETWORK_IN_TX`，[P8.4](08-outbound-http.zh.md)）属于编程错误。它们以通用的 `INTERNAL` 错误体离开进程（P4.3）：code 为 `INTERNAL` 的 reason 永远不给调用方看，只出现在日志行的 `error.reason` 里；测试构建里它直接让测试中止，好让错误在开发期就暴露。

## 说明

- 机器可读的 reason 让错误可测（测试断言 `CUSTOMER_CODE_TAKEN`，而不是一句话），也让前端可以翻译，用户的语言归前端管。
- 服务端渲染的文本只存在于不经过前端的地方（通知、打印的单据），使用接收方的 `locale`（[P5.5](05-identity.zh.md)）。
