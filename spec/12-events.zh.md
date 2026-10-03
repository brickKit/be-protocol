[English](12-events.md) · [中文](12-events.zh.md)

# P12 事件

事件在线上是什么样、怎么传递：CloudEvents 信封、outbox、流、durable 消费者、聚合流游标、两种 handler、死信、防环、尽力而为的信号、回放和总线适配器。Schema：[`envelope.schema.json`](../schemas/envelope.schema.json)、[`events-contract.schema.json`](../schemas/events-contract.schema.json)；表：`besdk_outbox`、`besdk_event_cursor`（[ddl/](../ddl/)）。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P12.1 | MUST | 发布只经 outbox：`besdk_outbox` 行与业务变更在**同一个事务**里写入。泵在任何事务之外发布，只有在总线确认已存储该消息（JetStream `PubAck`）之后，才把行标成 `PUBLISHED`。总线不可用时行留在 `PENDING`，在 `next_attempt_at` 重试，退避从 1 s 到 1 min；行**永不丢弃**，积压可在 `be_outbox_pending` / `be_outbox_oldest_age_seconds` 中看到。行用 `FOR UPDATE SKIP LOCKED` 认领（认领语句在 [ddl/](../ddl/) 里）；认领过期的行会再次发布，重复窗口会丢掉副本。轮询间隔自适应：忙时每 200 ms 一次，空闲时每 2 s 一次。最多 256 个确认同时在途 | CP-EVP-01, CP-EVP-02, CP-EVP-03, CP-EVP-04 |
| P12.2 | MUST | payload 是一个 JSON 对象，用组件的契约 `contracts/events/*.events.json`（[schema](../schemas/events-contract.schema.json)）校验；每个事件条目声明 `x-aggregate-type` 和 `x-consumption`（`state` 或 `sequence`）。payload 保持在 64 KiB 以下：会让它超过的内容放进生产者自己的桶，事件携带 **claim check** `{key, sha256, size}`（对象键、内容的 SHA-256 小写十六进制、字节数；形状见事件契约 schema 的 `$defs/claim_check`）；消费者从生产者契约里的一个 rpc 拿到短时有效的 URL，从不直接读桶（[P17.3](17-object-storage.zh.md)）。硬上限是 1 MiB，在发布时强制，并给出清楚的错误。payload 从不携带密钥或 token，个人数据只带消费者需要的最少部分；它从不原样展示给人看 | CP-EVP-05 |
| P12.3 | MUST | subject 为 `<domain>.<name>.<event…>.v<n>`：至少四段，第一段是领域（它决定流），第二段是组件或聚合的名字，最后一段是 n ≥ 1 的 `v<n>`。每一段都匹配 `[a-z][a-z0-9]*(_[a-z0-9]+)*`：小写、以字母开头、单词之间用单个下划线，不能以下划线开头或结尾、不能有连续下划线、不能有连字符（[`envelope.schema.json`](../schemas/envelope.schema.json)，向量 `envelope`）。保留较早的第一段 `sales` 和 `finance`。一个 subject 由一个组件发布，或由一个槽位族的每个成员发布；唯一的例外是 `infra.authz.relation.sync.v1`，由每个拥有关系的组件发布（[P6.13](06-authorization.zh.md)）。同一个生产者的同一个聚合类型的所有 subject，共用一个严格递增的聚合版本 | CP-EVP-01 |
| P12.4 | MUST | 流：每个 subject 第一段一个流，名为 `BE_<FIRST SEGMENT IN CAPITALS>`，subjects 为 `<first segment>.>`。默认值：`max_age` 7 天，`max_bytes` 1 GiB，`discard: old`，`duplicate_window` 10 min，文件存储，1 个副本。死信：流 `BE_DLQ`，subjects `dlq.>`，30 天。"没有就建，有就从不改"，在平台迁移时执行，启动时再执行一次；找不到流又无权创建的组件，迁移失败并指出流名 | CP-EVP-04 |
| P12.5 | MUST | durable：每个（组件，subject）一个 pull 消费者，名为 `<component ID with / as _>__<subject with every . as __>`（`erp_finance__sales__order__created__v1`），单跑、外壳里和每个副本上都相同。这个推导是单射：组件 ID 不含 `_`，而按 P12.3 subject 的任何一段都不含 `__`、也不以 `_` 开头或结尾，所以名字在每个 `__` 处都能唯一地切回去（`crm.lead.stage_changed.v1` 和 `crm.lead_stage.changed.v1` 的名字不同；向量 `envelope`）。服务端配置：`ack_wait` 30 s（真实值，从不为了覆盖退避而调大）；`max_ack_pending` 256；`max_deliver` −1（不限）且服务端**不设** `backoff`，因为投递次数由运行时来数、延迟由运行时来施加（P12.7）：设置了 `EVENTS_MAX_DELIVER` / `EVENTS_BACKOFF` 时取它们，否则取订阅自己的，再否则为 8 和 `1s,10s,1m,5m,15m,30m,1h`；首次创建时 `DeliverAll`；`inactive_threshold` 30 天。durable 只在不存在时创建，**从不更新**：运行时先查，没有才建；它从不发出会改动已有 durable 的"创建或更新"调用（运维改过的配置保留） | CP-EVS-01, CP-EVS-08 |
| P12.6 | MUST | 去重靠**聚合流游标**：`besdk_event_cursor`，主键 `(consumer, aggregate_type, aggregate_id)`。游标用 [ddl/](../ddl/) 里的 upsert 推进，与 handler 的写入在同一个事务里；没有返回行，表示重复或更旧的版本，该事件被跳过并确认。状态模式：handler 把它的投影推进到聚合在第 v 版时的状态。乱序和重复的投递，最终状态与按序投递一次相同 | CP-EVS-02, CP-EVS-03 |
| P12.7 | MUST | 两种 handler。**Apply** 在游标的事务里运行，只做本地写。**Run** 在任何事务之外运行，可以走网络，按业务键幂等，成功后用一个短事务推进游标。handler 出错就做一次带延迟 `EVENTS_BACKOFF[n − 1]` 的否定确认（用完了就一直取最后一个值），n 是 broker 对这条消息的投递计数。收到消息时、在任何 handler 运行之前，投递计数超过 `EVENTS_MAX_DELIVER` 的消息进死信；永久错误（payload 无法解析、违反契约、缺 `ce-id`）也立即进死信。进死信就是发布到 `dlq.<durable>.<original subject>`，消息 ID 为 `dlq:<durable>:<stream sequence>`（在这次发布和下一步之间崩溃也不会重复），带原来的 `ce-*` 头，外加 `be-dlq-reason`、`be-dlq-consumer`、`be-dlq-delivery`；然后终止原消息（`Term`） | CP-EVS-04, CP-EVS-05, CP-EVS-08 |
| P12.8 | MUST | `ce-hopcount` 大于 **10** 的入站事件进死信（防环）。在处理事件或运行 job 时发布的事件，`ce-causationid` = 被处理事件的 `ce-id`，`ce-hopcount` = 它的跳数 + 1，由运行时派生；从用户请求发出的，跳数为 0，且没有 `ce-causationid` | CP-EVS-06 |
| P12.9 | MUST | 慢 handler 每 `ack_wait / 3`（10 s）报告一次进度（JetStream `InProgress`）。每个订阅同时最多处理 4 条消息，同时受成员连接预算的约束。handler 的截止时间是 `ack_wait − 5 s`，`ack_wait` 就是 P12.5 的真实 30 s。正确性从不依赖 broker 的顺序 | CP-EVS-01 |
| P12.10 | MUST | 尽力而为的信号（即时信号，poke），比如 `infra.authz.changed.v1`：NATS 上用 core publish，PostgreSQL 队列上用 `NOTIFY`；不存储、不重投、可能丢失；每个使用者同时也轮询。外壳里每个成员各自订阅 | — |
| P12.11 | MUST（生产者保留 outbox 14 天） | 回放分三档：在流的保留期（7 天）以内，建一个从某个时间点开始的临时消费者；超出流的保留期、仍在 outbox 保留期（发布后 14 天）以内，从生产者的 outbox 重新发布，消息 ID 加后缀以避开重复窗口，消费者靠自己的游标去重；更早的历史不作为事件回放：新消费者从生产者的 `List` 回填（[P15.3](15-snapshots.zh.md)），区间答 `RANGE_COLD` 的部分，从生产者发布的数据集回填 | — |
| P12.12 | MUST | 总线适配器由 `EVENT_BUS_URL` 的 scheme 选择（没有时退回 `NATS_URL`）：`nats://` 为 JetStream（默认）；`postgres://…?schema=be_bus` 为 PostgreSQL 队列（表在 [ddl/be_bus.sql](../ddl/be_bus.sql) 里，由项目的数据库初始化创建）；`kafka://` 预留。一个项目的所有组件使用同一个适配器。每个适配器都保持 P12.5 和 P12.7 的投递语义（投递计数、运行时一侧的延迟、超过 `EVENTS_MAX_DELIVER` 进死信、不存在才建 durable），并通过 `brickKit/be-acceptance` 的总线套件 `conformance/bus/` | — |
| P12.13 | MUST | 总线客户端：永远重连，每 2 s 一次，加抖动；启动时总线没起来也持续重试；连接以成员的组件 ID 命名；断开、重连和异步错误用成员的 logger 记录。外壳里每个进程一条总线连接 | CP-CORE-03 |
| P12.14 | MUST | 不读取旧版信封：只有 `X-` 头、或没有 `ce-id` 的消息违反契约，进死信 | CP-EVS-04 |
| P12.15 | MUST | outbox 在发布后保留行 14 天，然后由生命周期引擎删除所有行都是 `PUBLISHED` 的整个分区。30 天未见的游标行被删除 | — |
| P12.16 | MUST | `component.yaml` 为 brickKit（≥ v1.3.0）声明组件的事件，brickKit 在 `brickkit graph`、`deps` 和 `lint` 里展示它们：`events.publishes` 恰好列出组件事件契约里的主题（槽位族成员列族的主题），`events.subscribes` 列出组件经 durable（P12.5）消费的每个主题，与它 `conformance/fixtures.yaml` 里的 `events.consumes` 是同一组。这一段由 be-ops 从这两个文件生成。P12.3 的主题原样就是合法的 brickKit 事件名。订阅项是确切的主题；brickKit 结尾 `*` 的前缀写法只能用在 `subscribes` 里，而且只用于真的按前缀订阅的消费者；尽力而为的 poke（P12.10）不列。这一段在运行时什么都不改：门禁 `events-declaration-scan` 把它与契约和夹具比对，套件把它与组件实际发布的主题和它建的 durable 比对 | CP-EVP-06、CP-EVS-09 |

## 信封

CloudEvents 1.0 二进制模式：信封在消息头里，payload 是业务 JSON 对象，别无他物。NATS 和 Kafka 把它们作为头携带；PostgreSQL 队列把它们存在 `be_bus.message.headers` 里。头名小写；扩展名只用小写字母和数字。

| 头 | 值 | 谁填 | 必填 |
|---|---|---|---|
| `ce-specversion` | `1.0` | 运行时 | 是 |
| `ce-id` | 事件 ID，一个 UUIDv7 = `besdk_outbox.id`；也是 broker 消息 ID（`Nats-Msg-Id`） | 运行时 | 是 |
| `ce-source` | 生产者组件的 ID；在外壳里是成员的 | 运行时 | 是 |
| `ce-type` | subject，如 `erp.sales.order.confirmed.v1` | 生产者 | 是 |
| `ce-time` | `occurred_at`，RFC 3339 UTC | 运行时 | 是 |
| `ce-subject` | 聚合 ID | 生产者 | 是 |
| `content-type` | `application/json`（二进制模式的 `datacontenttype`） | 运行时 | 是 |
| `ce-dataschema` | `<component ID>@<version>/contracts/events/<file>#<subject>`，是引用，不是可下载的 URL | 运行时 | 是 |
| `ce-aggregatetype` | 契约里的 `x-aggregate-type`（`erp.sales.order`） | 运行时，从契约取 | 是 |
| `ce-aggregateversion` | 本次变更之后聚合的版本，十进制整数 | 生产者 | 是 |
| `ce-causationid` | 正在处理的事件的 `ce-id` | 运行时 | 事件由另一个事件引起时（从请求发出时没有） |
| `ce-hopcount` | 引起它的事件的跳数 + 1；从请求发出时为 0 | 运行时 | 是 |
| `ce-legalentity` | 交易单据的法人 | 运行时，从 payload 取 | 交易单据事件上必填 |
| `traceparent`, `tracestate` | 生产 span 的 W3C 追踪上下文 | 运行时 | outbox 行带有 `traceparent` 时就带上（官方 SDK 总是带，[P18.1](18-observability.zh.md)）；消费者接受它缺失 |
| `ce-sequence` | 预留给 sequence 模式 | 不设置 | — |
| `ce-tenantid` | 预留；一个部署就是一个租户 | 不设置 | — |
| `Nats-Msg-Id` | 等于 `ce-id`（JetStream 重复抑制） | 运行时 | NATS 上 |

死信消息额外加上 `be-dlq-reason`、`be-dlq-consumer`（durable 名）和 `be-dlq-delivery`（投递次数）。

## 消费模式

| 模式 | 消费者收到的 | 状态 |
|---|---|---|
| `state` | 不一定是每个版本，可能迟到，但从不比它已应用的更旧 | 默认 |
| `sequence` | 每个版本，按顺序；有缺口时等待 | 预留；1.0 未实现 |

## 说明

- 投递是至少一次；因为游标与写入在同一个事务里推进，效果上等于一次。不承诺恰好一次。
- 游标按聚合流而不是按 subject 作键，所以同一个聚合在不同 subject 上的事件永远不会被乱序应用：`cancelled`（v3）先于 `created`（v2）到达时，状态停在"已取消"，`created` 随后被跳过。
- durable 每次首次创建时都会投递流里还在的内容，所以新装的消费者最多能补上 7 天。
