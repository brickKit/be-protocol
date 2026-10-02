[English](18-observability.md) · [中文](18-observability.zh.md)

# P18 可观测性

每个组件不论用什么语言，都输出同样的 trace、日志行和指标名，所以一条查询对每个组件都适用，不论是独立运行还是在外壳里。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P18.1 | MUST | **Trace。** W3C Trace Context 和 Baggage。HTTP 和 gRPC 入站提取、出站注入（`traceparent`、`tracestate`、`baggage`）。事件在信封里携带生产方 span 的 `traceparent`；消费方开启一个**新的 trace，用 span link** 指向生产方的 span，而不是作为它的子 span。每个成员的 resource 属性：`service.name` = 组件 ID，`service.version` = 组件版本，`service.namespace` = 项目，`service.instance.id` = 容器或 pod，`deployment.environment`。导出用 OTLP/HTTP，发往 `OTEL_BASE_URL`；为空表示不导出，也不报错。每个请求、事件 handler 和作业运行都有一个带有效 trace ID 的 span，不导出时也一样，所以日志和 problem 响应体里总有 `trace_id`。在外壳里，每个成员有自己的 tracer provider 和 meter provider；导出器和传播器是共享的，并且只有外壳在所有成员都停止之后才关闭导出器。每个埋点（HTTP 服务端、gRPC 服务端和客户端、出站 HTTP、消费者）都显式拿到成员的 tracer provider、meter provider 和传播器，从不用进程级的全局对象；全局 tracer provider 只作兜底，带 `service.name` = 外壳自己的 ID，所以出现这个名字的 span，就说明有一个埋点漏掉了 | CP-OBS-01, CP-SHELL-04, CP-SHELL-09, CP-SHELL-10 |
| P18.2 | MUST | **日志。** 只写 stdout，一行一个 JSON 对象，每行最多 2 KiB。更长的行被缩短，并且**仍是一个合法的 JSON 对象**：信封字段以外的字符串值从最长的开始、在字符边界处截短，每个都以 `…[TRUNCATED]` 结尾，并加上字段 `truncated: true`；信封字段从不截短。字段见[下表](#日志字段)。`LOG_LEVEL` 按成员设定最低级别。个人数据的键由运行时自动脱敏，从不靠业务代码，语义以一致性向量 `redaction` 为准（它是规范性的）：键被切成单词（snake_case、camelCase，`-` 和 `.` 也是分隔符，不分大小写）；某个受保护名字的单词在其中连续出现时就算受保护（最后一个单词允许带复数 `s`），所以 `contact_phone`、`phone_number`、`accessToken` 命中，`telephone`、`tokenizer` 不命中；整个值不论类型都变成字符串 `[REDACTED]`；值和信封字段从不扫描。受保护的名字：`phone`、`mobile`、`id_card`、`password`、`bank_card`、`email`、`token`、`secret`、`authorization`、`cookie`、`set_cookie`、`api_key` | CP-OBS-02, CP-OBS-04, CP-OBS-05 |
| P18.3 | MUST | **指标。** Prometheus 文本格式，在主端口的 `/metrics` 上。每个序列都带标签 `component=<component ID>`，独立运行时也一样。HTTP 的 `route` 是路由模板，从不是原始路径；状态码是数字。协议指标名以 `be_` 开头（见下表）；组件自己的指标以它的 domain 和 name 开头（`erp_sales_…`）。在外壳里，每个成员的 registry 汇总在外壳自己的 `/metrics` 上，各自带着 `component` 标签 | CP-OBS-03, CP-SHELL-04 |
| P18.4 | MUST | 受保护路由的访问日志行带 `sub` 和 `perm`，这样一个被拒的请求可以追到某个人和某个键。原始 token 从不出现在任何日志行里 | CP-OBS-02 |

## 日志字段

| 字段 | 何时出现 | 内容 |
|---|---|---|
| `time` | 总是 | RFC 3339 UTC，纳秒 |
| `level` | 总是 | `debug`、`info`、`warn`、`error` |
| `msg` | 总是 | 事件名或一句话；访问日志为 `http_request`，gRPC 访问日志为 `grpc_request` |
| `component_id`、`component_version` | 总是 | 在外壳里取成员自己的值 |
| `trace_id`、`span_id` | 有活动 span 时 | 访问日志行上必须有 |
| `request_id` | 请求内 | — |
| `sub` | 验签之后 | 从不放 token |
| `act` | 有代理链时 | JSON |
| `caller` | 系统面上 | `be-caller` |
| `perm` | 受保护路由上 | 本次判定的键 |
| `event_id`、`subject`、`delivery` | 事件 handler 里 | — |
| `job` | 作业里 | — |
| `error`、`error.code`、`error.reason` | 出错时 | `error` 是错误文本；它和所有值一样不被扫描，所以代码从不把个人数据写进错误文本 |
| `http.request.method`、`http.route`、`http.response.status_code`、`duration_ms` | 访问日志 | OpenTelemetry 语义约定的名字 |
| `rpc.service`、`rpc.method`、`rpc.grpc.status_code`、`duration_ms` | gRPC 日志 | 同上 |

错误的日志级别由运行时根据错误码决定（[P4.6](04-errors.zh.md)）。

## 指标名

| 名字 | 类型 | 标签（`component` 之外） |
|---|---|---|
| `be_http_server_requests_total` | counter | `method`、`route`、`status_code` |
| `be_http_server_duration_seconds` | histogram | `method`、`route` |
| `be_http_client_requests_total` | counter | `target`、`method`、`status_code` |
| `be_http_client_duration_seconds` | histogram | `target`、`method` |
| `be_grpc_server_handled_total` | counter | `service`、`method`、`code` |
| `be_grpc_server_duration_seconds` | histogram | `service`、`method` |
| `be_grpc_client_handled_total` | counter | `target`、`method`、`code` |
| `be_grpc_client_duration_seconds` | histogram | `target`、`method` |
| `be_outbound_inflight` | gauge | `target` |
| `be_db_pool_in_use` | gauge | — |
| `be_db_pool_wait_seconds` | histogram | — |
| `be_tx_retries_total` | counter | `reason` |
| `be_db_identity_ok` | gauge | — |
| `be_outbox_pending` | gauge | — |
| `be_outbox_oldest_age_seconds` | gauge | — |
| `be_events_published_total` | counter | `subject` |
| `be_consumer_handled_total` | counter | `subject`、`result`（`applied`、`skipped`、`nak`、`dlq`） |
| `be_consumer_lag_seconds` | gauge | `subject` |
| `be_dlq_messages_total` | counter | `subject` |
| `be_authz_bundle_age_seconds` | gauge | — |
| `be_authz_projection_lag` | gauge | — |
| `be_authz_denied_total` | counter | `reason` |
| `be_cache_hits_total`、`be_cache_misses_total`、`be_cache_evictions_total` | counter | `name` |
| `be_cache_entries` | gauge | `name` |
| `be_job_runs_total` | counter | `job`、`result` |
| `be_job_duration_seconds` | histogram | `job` |
| `be_job_last_success_timestamp_seconds` | gauge | `job` |
| `be_queue_depth` | gauge | `kind`、`state` |
| `be_queue_oldest_age_seconds` | gauge | `kind` |
| `be_reconcile_pending` | gauge | `name` |
| `be_reconcile_oldest_age_seconds` | gauge | `name` |
| `be_reconcile_giveups_total` | counter | `name` |
| `be_lifecycle_blocked` | gauge | `table`、`reason` |

## 说明

- 用 span link 而不是子 span，可以防止很长的异步链路长成一个没有边界的 trace（OpenTelemetry 消息语义约定）。
- 审计记录不是应用日志：它们是在业务事务里写下的事件，由一个审计组件消费。
