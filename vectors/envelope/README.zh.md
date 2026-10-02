[English](README.md) · [中文](README.zh.md)

# 语义向量：envelope

事件 id、CloudEvents 头、causation 与 hop、消费方如何处置一条消息、状态模式游标、重投，以及流、durable、死信 subject 的命名（协议 P11.5、P12；foundations 04、12、13）。对应 SDK API：outbox 泵、订阅运行时和 `IDTime`；下面的操作是它们内部的纯函数。

## 文件

| 文件 | 用例数 | 操作 |
|---|---|---|
| `ids.json` | 20 | `uuid7` |
| `headers.json` | 14 | `envelope` |
| `derive.json` | 12 | `derive`、`enqueue_context` |
| `inbound.json` | 25 | `accept` |
| `cursor.json` | 19 | `cursor_sequence`、`redelivery` |
| `names.json` | 28 | `stream`、`durable` |

## 操作

| 操作 | 输入 | 期望 |
|---|---|---|
| `uuid7` | `id` | `canonical`（小写）、`unix_ms`、`created_at`（= `IDTime(id)`，RFC 3339 UTC，毫秒） |
| `envelope` | `producer`（`component_id`、`version`、`events_file`）、`row`（一行 outbox：`id`、`subject`、`aggregate_type`、`aggregate_id`、`aggregate_version`、`occurred_at`、`traceparent`、`causation_id`、`hop_count`、`payload_json`），可选 `contract.transaction_document` | `headers`：完整的头，按名字排序，含 `Nats-Msg-Id` |
| `derive` | `context.kind`：`request`、`event`（带 `handled.id`、`handled.hop_count`）、`queued_job`（带作业行的 `causation_id`、`hop_count`）、`cron`、`singleton`、`every`、`reconciler` | 在那里发布的事件的 `causation_id`、`hop_count` |
| `enqueue_context` | 同上的 `context` | `job_causation_id`、`job_hop_count`：在那里入队时队列行存下的值 |
| `accept` | `subscription`（`component_id`、`subject`、`aggregate_type`、`transaction_document`）、`headers`、`payload_json`、`delivery` | `action: handle` 加解出的 `event`，或 `action: dlq` 加 `dlq_subject` 与 `added_headers`（`be-dlq-consumer`、`be-dlq-delivery`、`be-dlq-reason`） |
| `cursor_sequence` | `start`（游标当前版本或 `null`）、按顺序投递的 `versions[]` | `applied[]`（真正执行了 handler 的版本）、`final` |
| `redelivery` | `delivery`（从 1 开始，broker 的投递计数）、`max_deliver`、`backoff[]`（时长）、`outcome`：`ok`、`error`、`permanent`（投递超过 `max_deliver` 时忽略）、`durable`、`stream_seq` | `action`：`ack`、带 `delay` 的 `nak`，或带 `reason` 和 `dlq_msg_id` 的 `dlq`；`handled`：handler 是否运行 |
| `stream` | `subject` | `stream`（`BE_<第一段大写>`）、`filter`（`<第一段>.>`） |
| `durable` | `component_id`、`subject` | `durable`、`dlq_subject` |

## 规则

- **id**：36 个字符，十六进制加连字符，版本位 `7`，变体位 `10xx`；接受大写并转成小写（RFC 9562）；花括号、`urn:uuid:`、无连字符、带空白都是 `ID_INVALID`。分区表行的 `created_at` 就是 id 里 48 位的毫秒时间。
- **头**：`ce-specversion` 为 `1.0`；`ce-id` = `Nats-Msg-Id` = 行 id；`ce-source` 是生产者组件（外壳里是成员）；`ce-type` 是 subject；`ce-subject` 是聚合 id；`ce-time` = `occurred_at` 的 UTC 加 `Z`，只有非零时才带小数秒、去掉尾零、最多 6 位；`content-type: application/json`；`ce-dataschema` = `<component>@<version>/contracts/events/<file>#<subject>`；`ce-aggregatetype`、`ce-aggregateversion`（十进制，≥ 1）；`ce-hopcount` 总是出现；`ce-causationid` 与 `traceparent` 为空时不发；payload 的 `legal_entity_id` 是非空字符串时写 `ce-legalentity`。
- **交易单据事件**（事件契约里 `x-transaction-document: true`，此时 payload 必须要求 `legal_entity_id`）：缺了就不能发布（`LEGAL_ENTITY_MISSING`）；消费方收到头缺失或与 payload 不一致的，进死信。
- **派生**：来自请求或任何定时任务（cron、singleton、every、reconciler）：causation 为空、hop 为 0。在 handler 里：causation = 正在处理的 `ce-id`，hop = 它的 hop + 1。队列作业在入队时存下"此刻发布的事件会带的值"，执行时原样使用。发布永远不会因 hop 被拒。
- **接收**：死信原因有 `ENVELOPE_INVALID`（必填头缺失或格式错、`ce-specversion` 不对、`ce-type` 不是订阅的 subject、`ce-aggregatetype` 与契约不同、`content-type` 不是 JSON、整数带符号或前导零）、`HOP_LIMIT`（hop 大于 10）、`PAYLOAD_INVALID`（不是 JSON 对象）、`LEGAL_ENTITY_MISSING`。只有旧 `X-` 头的消息一律不读。
- **游标（状态模式）**：版本大于游标才执行；相等或更旧的跳过；任意乱序加重复投递，最终状态相同。
- **重投**（P12.5、P12.7）：broker 上的 durable 是 `max_deliver` −1、不设退避，由运行时决定。收到消息时，投递 `d > max_deliver` 不运行 handler，直接进死信（`MAX_DELIVER`）；否则失败的投递 nak 并延迟 `backoff[min(d, len) − 1]`，所以最后一次允许的投递 `d = max_deliver` 失败时仍然 nak；永久错误直接进死信（`PERMANENT`）。死信消息 ID 为 `dlq:<durable>:<stream sequence>`。
- **命名**：subject 至少四段（`<domain>.<name>.<event…>.v<n>`，P12.3），每段都是 `[a-z][a-z0-9]*(_[a-z0-9]+)*`（以字母开头；不能以下划线开头或结尾，不能有连续下划线，不能有连字符），最后一段是 `v<n>` 且 n ≥ 1。durable = 组件 id 的 `/` 换成 `_`，接 `__`，再接把每个 `.` 都换成 `__` 的 subject（`erp_finance__sales__order__created__v1`）。因为没有哪一段含 `__` 或以 `_` 开头、结尾，组件 id 也不含 `_`，名字能唯一地切回去：`crm.lead.stage_changed.v1` 和 `crm.lead_stage.changed.v1` 的名字不同。死信 subject = `dlq.<durable>.<subject>`。

## 错误

| 错误类 | 出现在 |
|---|---|
| `ID_INVALID` | `uuid7`、`envelope`（outbox 的 id） |
| `SUBJECT_INVALID`、`COMPONENT_INVALID` | `envelope`、`stream`、`durable` |
| `ENVELOPE_INVALID`、`LEGAL_ENTITY_MISSING` | `envelope`（发布时）；同名值也作为 `accept` 里的 `be-dlq-reason` |

## 本处补定的口径

请评审：`ce-time` 的精度规则；`ce-causationid` / `traceparent` 为空时不发头，而不是发空值；队列作业的 causation 在入队时捕获；`be-dlq-reason` 的取值表（`ENVELOPE_INVALID`、`HOP_LIMIT`、`PAYLOAD_INVALID`、`LEGAL_ENTITY_MISSING`、`MAX_DELIVER`、`PERMANENT`）；`be-dlq-consumer` 写 durable 名。另注意：`erp.x_y.done.v1` 与 `erp.x.y_done.v1` 会得到同一个 durable 名，subject 评审时要避免。

## 重新生成

`python3 gen/gen_envelope.py`；交叉验证 `node gen/xcheck_envelope.mjs .`。
