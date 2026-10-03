[English](README.md) · [中文](README.zh.md)

# 语义向量：errors

错误模型里可以计算的部分（协议 P4、P10.4；foundations 10、15、23）：码 ↔ 状态码、平台 reason、还原依赖返回的 REST 错误、SQLSTATE 归类、日志级别、problem+json 错误体、`Retry-After`、reason 命名。对应 SDK API：HTTP 的 `Fail` 路径、gRPC 错误拦截器、`UserHTTP` 的错误解码、`Store.Tx` 的重试循环、日志 handler。

## 文件

| 文件 | 用例数 | 操作 |
|---|---|---|
| `codes.json` | 66 | `grpc_to_http`、`be_reason`、`restore_http` |
| `sqlstate.json` | 23 | `classify` |
| `levels.json` | 34 | `log_level`、`access_log_level` |
| `problem.json` | 30 | `problem`、`retry_after`、`reason_name` |

## 操作

| 操作 | 输入 | 期望 |
|---|---|---|
| `grpc_to_http` | `code`（规范名），可选 `reason`、`domain` | `number`（gRPC 数字码）、`http` |
| `be_reason` | `reason`（平台 reason） | `code`、`domain: be`、`http` |
| `restore_http` | `status`、`problem`（依赖返回的 problem+json 成员，或 `null`） | 调用方看到的 `code`、`reason`、`domain`、`http` |
| `classify` | `sqlstate`、`attempt`（从 1 开始，可重试的状态才有）、`context`（`none`、`deadline_exceeded`、`cancelled`）、`component_mapping`（组件自己映射的 23505） | `action: retry` 加 `base_delay_ms`，或 `action: fail` 加 `code`、`reason`、`domain`、`http`，reason 带参数时还有 `metadata` |
| `log_level` | `code` | `level`：`error`、`warn`、`info` 或 `none` |
| `access_log_level` | 响应的 `code` | 访问日志行的 `level`：`error`、`warn` 或 `info` |
| `problem` | `error`（`code`、`reason`、`domain`、`metadata`、`violations`、`internal_message`）、`request`（`path`、`request_id`、`trace_id`） | `content_type`、`body`（除 `title`、`detail` 以外的全部成员，那两项来自文案目录）、`detail_must_not_contain[]` |
| `retry_after` | `code`、`retry_delay_ms` | `header`：`Retry-After` 的值，或 `null` |
| `reason_name` | `reason`、`domain` | `valid: true` |

## 规则

- **码 → 状态码**：foundations 15 的表：`INVALID_ARGUMENT`、`FAILED_PRECONDITION`、`OUT_OF_RANGE` 为 400；401、403、404；`ALREADY_EXISTS`、`ABORTED` 为 409；429；`CANCELLED` 为 499；`INTERNAL`、`UNKNOWN`、`DATA_LOSS` 为 500；501、503、504。唯一例外：`be` / `BODY_TOO_LARGE` 是 `INVALID_ARGUMENT`，但以 **413** 回答。
- **还原 REST 错误**：带已知 `code`、`reason` 与 `domain` 的 problem 体原样保留。没有时按状态码取码（400、413 → `INVALID_ARGUMENT`；401；403；404；409 → `ABORTED`；429；499；501；502、503 → `UNAVAILABLE`；504；其它 4xx → `FAILED_PRECONDITION`；其它 5xx → `UNKNOWN`），`reason` / `domain` 为 `null`。
- **SQLSTATE**：`40001`、`40P01` 在 `10 ms · 2^(attempt−1)` 加抖动之后重跑事务函数，总共最多 3 次；第三次失败是 `ABORTED` / `TX_CONFLICT`。`55P03` → `ABORTED` / `LOCK_TIMEOUT`。`57014` → `DEADLINE_EXCEEDED` / `STATEMENT_TIMEOUT`，除非是请求本身被取消（`CANCELLED` / `REQUEST_CANCELLED`，499）。`25P04` → `STATEMENT_TIMEOUT`。`53300` → `UNAVAILABLE` / `DB_TOO_MANY_CONNECTIONS`。连接断开或连不上（`08` 类、`57P01`、`57P02`、`57P03`）→ `UNAVAILABLE` / `DEPENDENCY_UNAVAILABLE`，`metadata.dependency = db`。组件自己映射的 `23505` 保留组件的 reason。其它一切（含 `25P03`、`42501`）都是 `INTERNAL`。
- **级别**：`INTERNAL`、`UNKNOWN`、`DATA_LOSS` → error；`UNAVAILABLE`、`DEADLINE_EXCEEDED` → warn；`CANCELLED` 与 `OK` → 不记；调用方错误 → info。响应的访问日志行：三个隐藏码为 error，`UNAVAILABLE`、`DEADLINE_EXCEEDED` 为 warn，其余（含 `OK`、`CANCELLED`）为 info。
- **problem+json**：`type` = `urn:be:<domain>:<reason>`；`status` 查表；`code` 是规范名；`instance` 是路径；`request_id`、`trace_id` 总是出现。`INTERNAL`、`UNKNOWN`、`DATA_LOSS`、没有码的错误、有 reason 却没有 domain 的错误，一律答 `reason: INTERNAL`、`domain: be`、空 `metadata`、无 `violations`，`detail` 不含原始消息的任何部分（`UNKNOWN`、`DATA_LOSS` 保留自己的 `code`）。`metadata` 的值只能是字符串。
- **Retry-After**：只随 429 和 503，且错误带延迟时才有；整秒，向上取整。
- **reason 命名**：`^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$`；组件不得在自己的 domain 里抛平台 reason 的名字。

## 错误

| 错误类 | 何时 |
|---|---|
| `CODE_UNKNOWN` | 不是规范码名（码名大写） |
| `METADATA_NOT_STRING` | `metadata` 里有非字符串的值 |
| `REASON_NAME_INVALID`、`REASON_RESERVED` | reason 不合命名规则，或在 `domain: be` 之外复用平台名 |

## 本处补定的口径

请评审：依赖不带 problem 体时用的状态码 → 码表（不臆造 reason：`null`）；请求被取消导致的 `57014` 映射为 `CANCELLED` / `REQUEST_CANCELLED`（rc.2：运行时回答的每个错误都带 reason）；有 reason 无 domain 的错误按未归类处理；`UNKNOWN` / `DATA_LOSS` 保留自己的码，reason 变为 `INTERNAL`；平台自身的 `type` 是 `urn:be:be:<REASON>`；`title`、`detail` 文案不在这里锁定，它们来自文案目录（`schemas/errors-be.yaml`、各组件的 `contracts/errors.yaml`）。

## 重新生成

`python3 gen/gen_errors.py`；交叉验证 `go run gen/xcheck_errors.go .`。
