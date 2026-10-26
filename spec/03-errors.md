# 03 错误对象与原因目录

依据：装配项目的“组件间调用与错误”（一个错误对象、reason 目录、内部错误不外泄、不可见答 404），安全 09a 的“求值结果与错误”。

## 一个错误对象

| 编号 | 层级 | 规则 | 检验 |
| --- | --- | --- | --- |
| P3.1 | 必须 | 用户面每个 4xx、5xx 响应的 `Content-Type` 是 `application/problem+json`，正文符合 `schemas/problem.schema.json`（下表）；运行时产生的每个错误都有 `reason` 与 `domain` | CK-ERR-01 |
| P3.2 | 必须 | 系统面的错误是 `google.rpc.Status`：`code` 为下表的 gRPC 码，`details` 恰好含一个 `google.rpc.ErrorInfo`（`reason`、`domain`、`metadata` 与用户面相同）；字段错误另含一个 `google.rpc.BadRequest` | CK-ERR-02 |
| P3.3 | 必须 | 同一个错误穿过系统面、用户面与移动聚合的 GraphQL（放在 `extensions`）时，`reason`、`domain`、`metadata` 不变 | CK-ERR-03 |
| P3.4 | 必须 | 内部错误一律回答 `reason` `INTERNAL`、`domain` `be`、一句通用的 `detail` 与 `trace_id`；原始错误（SQL、栈、库的报错）只进日志 | CK-ERR-04 |
| P3.5 | 必须 | 调用者看不到的记录答 `NOT_FOUND`，读取与命令一致；对无权的调用者，错误内容不含金额、负责人、角色内容或证明细节 | CK-ERR-05 |
| P3.6 | 必须 | 需要调用方稍后重试的错误带 `Retry-After` 响应头（秒，整数）；系统面带 `google.rpc.RetryInfo` | CK-ERR-06 |
| P3.7 | 必须 | `reason` 是大写下划线；`domain` 是产生它的组件 ID（`erp/inventory`），平台保留的 reason 用 `be`；槽位族的成员用族的 ID（每个授权成员都答 `infra/authz`）。组件自己的 reason 在契约中声明、只追加 | 装配检查 |
| P3.8 | 应当 | 服务端不翻译：`title` 与 `detail` 用部署的缺省语言，前端按 `reason` 与 `metadata` 显示自己的文本 | — |

**用户面错误体**：

| 字段 | 必有 | 内容 |
| --- | --- | --- |
| `type` | 是 | `urn:be:<domain>:<reason>` |
| `title` | 是 | reason 的简短标题 |
| `status` | 是 | HTTP 状态码 |
| `detail` | 是 | 给人看的一句话；`INTERNAL` 时是通用文案 |
| `reason` | 是 | 原因 |
| `domain` | 是 | 产生它的组件 ID，或 `be` |
| `metadata` | 否 | 字符串到字符串的映射（与 AIP-193 一致：数字与日期由产生方格式化） |
| `trace_id` | 是 | 本次请求的追踪 ID（W3C trace-id，32 位小写十六进制） |
| `violations` | 否 | 字段错误：每项 `field`（JSON 指针）、`reason`、`description` |

## 码与状态

一个 reason 对应一个 gRPC 码；gRPC 码到 HTTP 状态按下表，个别 reason 另有指定（见目录的 HTTP 列）。

| gRPC 码 | HTTP | gRPC 码 | HTTP |
| --- | --- | --- | --- |
| `INVALID_ARGUMENT`、`FAILED_PRECONDITION`、`OUT_OF_RANGE` | 400 | `RESOURCE_EXHAUSTED` | 429 |
| `UNAUTHENTICATED` | 401 | `CANCELLED` | 499 |
| `PERMISSION_DENIED` | 403 | `UNIMPLEMENTED` | 501 |
| `NOT_FOUND` | 404 | `UNAVAILABLE` | 503 |
| `ALREADY_EXISTS`、`ABORTED` | 409 | `DEADLINE_EXCEEDED` | 504 |
| `INTERNAL`、`UNKNOWN`、`DATA_LOSS` | 500 | | |

| 编号 | 层级 | 规则 | 检验 |
| --- | --- | --- | --- |
| P3.9 | 必须 | 日志级别按 gRPC 码：`INTERNAL`、`UNKNOWN`、`DATA_LOSS` 为 ERROR；`UNAVAILABLE`、`DEADLINE_EXCEEDED` 为 WARN；`CANCELLED` 不按错误记；其余（调用方的错误）为 INFO。访问日志按 HTTP 状态：500 为 ERROR，503 与 504 为 WARN，其余为 INFO | 向量 `errors` |

## 平台原因目录（`domain` 为 `be`）

“可重试”指调用方可以用同一个幂等键再试；“查询后再定”指先查询结果再决定。授权类各项的含义与使用场合以装配项目安全 09a 为准。

| reason | gRPC 码 | HTTP | 可重试 | 含义 |
| --- | --- | --- | --- | --- |
| `REQUEST_INVALID` | `INVALID_ARGUMENT` | 400 | 否 | 请求解不开或不符合操作的 schema；字段错误在 `violations` |
| `BODY_TOO_LARGE` | `INVALID_ARGUMENT` | 413 | 否 | 请求体超过路由的上限 |
| `CURSOR_INVALID` | `INVALID_ARGUMENT` | 400 | 否 | 游标与请求不匹配或解不开 |
| `BATCH_TOO_LARGE` | `INVALID_ARGUMENT` | 400 | 否 | 按身份批量读取超过契约上限；拒绝而不截断 |
| `TOKEN_INVALID` | `UNAUTHENTICATED` | 401 | 否 | 没有令牌，或签名、签发方、受众、类型、有效期不符 |
| `TOKEN_STALE` | `UNAUTHENTICATED` | 401 | 边缘换取新令牌后一次 | 身份侧的事实已变（会话代次、安全状态版本） |
| `SERVICE_CREDENTIAL_INVALID` | `UNAUTHENTICATED` | 401 | 否 | 系统面调用没有有效的服务身份 |
| `PERMISSION_DENIED` | `PERMISSION_DENIED` | 403 | 否 | 可见但没有此操作的资格；命令的目标取值越界 |
| `CONTAINMENT_NOT_PROVEN` | `PERMISSION_DENIED` | 403 | 否 | 包含证明不成立（安全 09a） |
| `NOT_FOUND` | `NOT_FOUND` | 404 | 否 | 不存在或不可见 |
| `QUERY_NOT_COMPLETABLE` | `FAILED_PRECONDITION` | 422 | 否 | 有段不可下推、候选集超预算、冷层没有覆盖 |
| `FIELD_NOT_QUERYABLE` | `FAILED_PRECONDITION` | 422 | 否 | 受限字段不可用于此查询 |
| `QUERY_PLAN_CHANGED` | `ABORTED` | 409 | 否（重新查询） | 游标的计划摘要不一致 |
| `CHANGE_KEY_CONFLICT` | `ALREADY_EXISTS` | 409 | 否 | 同一变更键、不同的内容 |
| `CHANGE_REVISION_STALE` | `ABORTED` | 409 | 否（重新预览） | 生效点发现修订已变 |
| `LAST_ADMIN_PROTECTED` | `FAILED_PRECONDITION` | 409 | 否 | 最后管理员保护 |
| `IDEMPOTENCY_KEY_REUSED` | `INVALID_ARGUMENT` | 422 | 否 | 同一幂等键用于不同的命令、目标或请求体 |
| `IDEMPOTENCY_IN_PROGRESS` | `ABORTED` | 409 | 是 | 这个键的第一次使用还没结束 |
| `LOCK_TIMEOUT` | `ABORTED` | 409 | 是 | 锁等待超过事务的锁超时 |
| `TX_CONFLICT` | `ABORTED` | 409 | 是 | 自动重试之后仍有序列化冲突 |
| `STATEMENT_TIMEOUT` | `DEADLINE_EXCEEDED` | 504 | 是 | 语句或事务超过它的超时 |
| `SERVICE_BUSY` | `UNAVAILABLE` | 503 | 是 | 前台等待超过时限（队列已满或连接预算用尽）；带 `Retry-After`；`metadata.resource` 为 `queue` 或 `db_pool` |
| `OUTBOUND_LIMIT` | `RESOURCE_EXHAUSTED` | 503 | 是 | 对同一个依赖的并发出站已满，立即失败；`metadata.dependency` |
| `CIRCUIT_OPEN` | `UNAVAILABLE` | 503 | 是 | 对该依赖的熔断打开，未发出；`metadata.dependency` |
| `DEPENDENCY_UNAVAILABLE` | `UNAVAILABLE` | 503 | 是 | 需要的依赖连不上；`metadata.dependency` 为 `db`、`bus`、`blob` 或组件（族）ID |
| `DEADLINE_BUDGET_EXHAUSTED` | `DEADLINE_EXCEEDED` | 504 | 否 | 剩余时间不足以发出调用，未发出 |
| `DEADLINE_EXCEEDED` | `DEADLINE_EXCEEDED` | 504 | 查询后再定 | 请求的截止时间到了 |
| `REQUEST_CANCELLED` | `CANCELLED` | 499 | — | 调用方取消了请求；不按错误记日志 |
| `NOT_READY` | `UNAVAILABLE` | 503 | 是 | 进程不在就绪状态（[01](01-lifecycle-and-health.md) 的 P1.6） |
| `AUTHORIZATION_UNPROVABLE` | `UNAVAILABLE` | 503 | 是 | 授权无法证明（来源不可得、超期、修订不相容） |
| `AUTHORIZATION_VIEW_EXPIRED` | `UNAVAILABLE` | 503 | 是 | 授权视图超过有效期 |
| `RECOVERY_IN_PROGRESS` | `UNAVAILABLE` | 503 | 是 | 部署待恢复 |
| `MEMBER_SWITCH_IN_PROGRESS` | `UNAVAILABLE` | 503 | 是 | 授权或身份成员切换中 |
| `DEFINITION_PENDING` | `UNAVAILABLE` | 503 | 是 | 安全变更引用的资源类型还没有已被接受的定义：组件就绪不等定义被接受（[08](08-identity-authz-audit.md) 的 P8.24），定义还在提交中；不占用变更键，同一个键稍后重新提交 |
| `CAPABILITY_UNSUPPORTED` | `UNIMPLEMENTED` | 501 | 否 | 声明了不支持的能力；`metadata.capability` |
| `RESULT_UNKNOWN` | `DEADLINE_EXCEEDED` | 504 | 查询后再定 | 用变更键或动作键查询，不换键重试 |
| `AUDIT_CAPACITY_EXHAUSTED` | `UNAVAILABLE` | 503 | 是 | 本地审计表的积压超过容量上限，新的必需审计操作暂停（[08](08-identity-authz-audit.md) 的 P8.23） |
| `INTERNAL` | `INTERNAL` | 500 | 否 | 任何内部错误；原始错误被隐藏 |

`OUTBOUND_LIMIT` 的 HTTP 状态指定为 503 而不是 429：它表示调用方自己的出站预算用尽，不是被对方限流。

安全 09a 中返回 202 的两项（`CONFIRMATION_REQUIRED`、`ADMIN_AVAILABILITY_UNPROVABLE`）是处理结果而不是错误，随授权章节写入；`HELD_BY_SECURITY_DISPOSITION` 只出现在解释中，对外按无权表达。

**只进日志、不上线的分类**（对外一律 `INTERNAL`）：`NETWORK_IN_TX`（持有未结束的事务时发起出站调用）、`NESTED_TX`（事务中又开事务）。它们是编程错误，日志中带这个分类以便定位。
