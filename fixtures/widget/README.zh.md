[English](README.md) · [中文](README.zh.md)

# 夹具：widget

`conformance/widget` 是每门官方 SDK 都在 `examples/widget` 里实现一份、组件一致性套件（`tools/be-acceptance/conformance/component/`）拿来跑的组件。它很小，但碰到协议的每一个 profile，所以三门 SDK 在它上面通过同一套用例，就是三者等价的证据。它也是任何语言写组件时照抄的范本。本文是它的行为说明：每门 SDK 的 widget 必须做到什么，全部可从外面观察。

## 文件

| 文件 | 内容 |
|---|---|
| `component.yaml` | brickKit 清单：依赖、`configSchema`、端口（8080，grpc 9090）、迁移命令 |
| `assembly.yaml` | 协议键（`protocol`、`conformance`、`resources`）、权限、数据范围、边缘路由 |
| `contracts/widget.openapi.yaml` | 用户面；每个操作的守卫写在 `x-be-permission`，截止时间写在 `x-be-deadline-seconds` |
| `contracts/conformance/widget/v1/widget.proto` | 系统面 `conformance.widget.v1.WidgetService` |
| `contracts/events/widget.events.json` | 发布的三个 subject |
| `contracts/errors.yaml` | widget 自己的 reason |
| `migrations/0001_widget.sql` | 参考表结构；规范性的，因为 `conformance/fixtures.yaml` 用 SQL 观察这些表 |
| `migrations/lifecycle.yaml` | 每个生命周期类别一张表 |
| `conformance/fixtures.yaml`、`conformance/samples/` | 金样本 fixtures 文件及其载荷 |
| `broken-variants.yaml` | 故意写坏的构建，以及每个必须失败的用例 |

它的依赖 `conformance/peer` 只有契约：[../peer/](../peer/README.zh.md)。

## 表

| 表 | 类别 | 存什么 |
|---|---|---|
| `widgets` | document，按月分区 | 聚合本身；状态 `DRAFT → APPROVING → APPROVED`，或 `SUSPENDED` |
| `widget_lines` | 跟随 `widgets` | 明细行，`created_at` 等于所属部件的 |
| `widget_ledger` | ledger，立即封存 | 每次审批一条，无缺号编号 |
| `widget_audit` | audit，立即封存 | 每个命令、每次任务运行、每条处理过的事件一行 |
| `widget_jobs` | queue，按周分区 | 每条通知一行（`PENDING`、`SENT`、`DEAD`） |
| `owner_snapshots` | snapshot | conformance/peer 的 owner，按上游版本 |
| `widget_kinds` | reference | `STD`（10 行）、`BIG`（100 行），迁移时写入 |
| `widget_owners` | master，含个人信息 | 每个用户自己的资料（`display_name`、`phone`、`email`） |

## 用户面

路径都在 `/conformance/widget` 之下。

| 路由 | 守卫 | 行为 |
|---|---|---|
| `GET /kinds` | public | 参考数据；不带 token、bundle 还没加载时也能用 |
| `PUT /owners/me` | authenticated | 写入调用者自己的 `widget_owners` 行；记一行 `msg=owner_profile_updated`，带 `display_name`、`phone`、`email`（后两个必须输出为 `[REDACTED]`） |
| `POST /widgets` | `conformance.widget.create` | 一步式幂等的新建（指纹：除 `idempotency_key` 外的全部 body 字段）；`owner_id` = sub，`dept_path` 取 token 的；号码来自 `WIDGET_NO_FORMAT`（允许缺号）；`document_date` = 法人时区下的今天；`amount` = `round(quantity × price)`；outbox 写 `conformance.widget.created.v1`；201 |
| `GET /widgets` | `conformance.widget.view` | 规范范围谓词，覆盖 owner / org / region 加共享；游标分页；没有 `price.read` 时 `sort=price` 或 `amount` → 400 `SORT_FORBIDDEN`；`region=` 不在调用者取值内 → 403 `OUT_OF_SCOPE`；被掩码的字段为 `null` 并列进 `_masked`；每行带 `_access` |
| `GET /widgets/{id}` | `conformance.widget.view` | 看不见就 404；owner 显示名来自快照（读穿透 `BatchGetOwners`）；带 `X-Data-As-Of` |
| `GET /widgets/{id}/owner` | `conformance.widget.view` | 用 UserHTTP 调 `GET /conformance/peer/owners/{owner_id}`，转发 `Authorization`、`X-Request-Id`、`traceparent`、`X-Authz-Revision`，不带任何 `be-*` 头 |
| `POST /widgets/{id}/approve` | `conformance.widget.approve`，15 s | 下面的两段式命令 |
| `POST /widgets/{id}/slow?ms=&via=` | `conformance.widget.view`，2 s | 以 `sleep`、`db`（事务里 `pg_sleep`）或 `peer`（`GetReservationStatus`）等待 `ms`；超过 2 s → 504，下游工作被取消 |
| `POST /widgets/{id}/attachments` | `conformance.widget.attach` | 预签名 PUT，最长 5 分钟、最多 `size_bytes`（≤ 10 MiB）；对象键里没有文件名 |
| `GET /widgets/{id}/attachments/{attachment_id}` | `conformance.widget.view` | 预签名 GET，最长 5 分钟 |

字段键：设置 `price` 需要 `conformance.widget.price.edit`（403 `FIELD_FORBIDDEN`）；读 `price` 和 `amount` 需要 `conformance.widget.price.read`。运行时另外挂出运维端点、`_authz/*`、`_shares/*`（共享可选：provider 不支持时 501）和 `_lifecycle/*`。

## 审批

1. 对目标授权（看不见 404，看得见做不了 403），认领键（`CLAIMED`），要求 `DRAFT`（否则 400 `WIDGET_NOT_DRAFT`），置为 `APPROVING` 并设 `deadline_at = now + WIDGET_APPROVE_TIMEOUT`（30 s），提交。这一步对部件行加 `FOR UPDATE`（套件持锁时答 409 `LOCK_TIMEOUT`）。
2. 在任何事务之外调 `PeerService/Reserve`（幂等键 `widget-approve:<id>`，`hold_seconds` = `WIDGET_RESERVE_HOLD_SECONDS`），出站截止时间 `min(3 s, 剩余 − 50 ms)`，按 `IDEMPOTENT` 方法的重试策略。
3. 预留成功 → 一个事务：`APPROVED`、`approved_at`、`reservation_id`、版本 + 1；一条 `widget_ledger`，编号取 `WIDGET_LEDGER_NO_FORMAT`（按法人与会计期间无缺号）；outbox 写 `conformance.widget.approved.v1`；入队 `widget.notify`（`kind=approved`，唯一键 `approved:<id>`）；一行 `widget_audit`；键置 `DONE` 并存下响应。200。
4. 明确拒绝（`QUOTA_EXCEEDED`、`REJECTED`）→ 回到 `DRAFT`，释放认领，原样转达对方的错误及其 domain（400 `conformance/peer` / `QUOTA_EXCEEDED`）。
5. 结果未知（截止时间到、重试后仍 `UNAVAILABLE`）→ 202，部件为 `APPROVING`；键保持 `CLAIMED`，同一个键在调和器完成之前一律答 409 `IDEMPOTENCY_IN_PROGRESS`。

## 系统面

`conformance.widget.v1.WidgetService`：`GetWidget`、`BatchGetWidgets`（≤ 100 个 id，超过答 `BATCH_TOO_LARGE`）是 `NO_SIDE_EFFECTS` 的系统读，不过数据范围；`TouchWidget` 是 `IDEMPOTENT`（命名空间 `svc:<be-caller>`；`touch_count` + 1、一行审计、不发事件）；`GetTouchStatus` 按键回答；`ApproveWidget` 是面向用户的方法，经 gRPC 一律答 `UNAUTHENTICATED`。任何不带 `be-caller` 的调用答 `UNAUTHENTICATED` / `MISSING_CALLER`。

## 事件

| Subject | 方向 | 行为 |
|---|---|---|
| `conformance.widget.created.v1` | 发布 | 来自 `POST /widgets` |
| `conformance.widget.approved.v1` | 发布 | 来自审批第 3 步，可能由请求、也可能由调和器发出 |
| `conformance.widget.reverted.v1` | 发布 | 来自 `reservation.expired` 的 handler |
| `conformance.owner.updated.v1` | 消费，`Apply` | 带版本守卫的快照 upsert；旧版本或同版本什么都不改 |
| `conformance.reservation.expired.v1` | 消费，`Apply`，交易单据 | 持有该 `reservation_id` 的 `APPROVED` 部件回到 `DRAFT`，版本 + 1，并在同一事务里发布 `conformance.widget.reverted.v1`（causation = 处理中的 `ce-id`，hop + 1）；部件不是 `APPROVED` 或预留不是它的：不变 |

durable 名：`<实例 id 的 / 换成 _>__<subject 的每个 . 换成 __>`（`conformance_widget-go__conformance__owner__updated__v1`）。重投与死信按 `EVENTS_MAX_DELIVER` / `EVENTS_BACKOFF`。

## 后台工作

| 名字 | 种类 | 行为 |
|---|---|---|
| `widget.daily` | Cron `0 3 * * *`，按 `BUSINESS_TIMEZONE` | 写一行 `widget_audit`，`action=daily_summary`，带上一个业务日审批通过的部件数；`JOBS_OVERRIDES` 可改 `cron` 或 `enabled` |
| `widget.notify` | Worker（队列），5 次，退避 `1s,5s,30s,2m` | 用作业的唯一键调 `PeerService/Notify`，把 `widget_jobs` 行置 `SENT`；次数用尽时 `OnDead` 置 `DEAD` |
| `widget.approve` | Reconciler，每 5 s | 候选为 `deadline_at < now` 的 `APPROVING`；按键问 `GetReservationStatus`：已预留 → 第 3 步；没有 → 再 `Reserve`；被拒 → 第 4 步；5 次后放弃：`SUSPENDED`，键以挂起后的部件置 `DONE`（重放答 200），并入队 `widget.notify` `kind=exception` |
| `be.*` | 平台 | outbox、清理、生命周期、授权变更、快照；widget 不用声明 |

## 配置与降级

协议键见 `component.yaml`；widget 自己的：`WIDGET_NO_FORMAT`（默认 `WG{yyyy}{mm}-{seq:05}`）、`WIDGET_LEDGER_NO_FORMAT`（`WL-{le}-{yyyy}{mm}-{seq:06}`）、`WIDGET_APPROVE_TIMEOUT`（`30s`）、`WIDGET_RESERVE_HOLD_SECONDS`（`900`）。格式非法是配置错误（退出码 78，点名该键）。

`mdm/org` 是**可选**依赖。装了：法人日历（时区、会计年度起始月、代码）经 SDK 的快照帮手从它取。没装（套件从不装它）：`MDM_ORG_ENDPOINT` 不存在，widget 不崩，所有法人一律用 `BUSINESS_TIMEZONE`、起始月 1，并以 id 作 `{le}` 代码。这是 widget 对 P2.5 的演练。

## 套件需要知道的事

`conformance/fixtures.yaml` 遵循 `schemas/fixtures.schema.json`，用例需要的每个事实现在那里都有字段。各事实写在哪里：

| 用例范围 | `fixtures.yaml` 里的字段 | 对 widget |
|---|---|---|
| CP-AUTH-09 | 没有：守卫取自 OpenAPI 里的 `x-be-permission` | `public`：`GET /kinds`；`authenticated`：`PUT /owners/me` |
| CP-RPC-03 | operation 上的 `user_facing: true` | `ApproveWidget` |
| CP-DB-02 | `lock` | `SELECT 1 FROM widgets WHERE id = $1 FOR UPDATE`，审批期间一直持有 |
| CP-OBS-04 | `pii_log` | `PUT /owners/me` 会记 `phone` 和 `email` |
| CP-SCOPE-03、-09、-11 | 列表上的 `filters`、`sort` | 维度参数 `region`；排序参数 `sort`，被掩码的取值 `price`、`amount` |
| CP-EVS-06 | 被消费 subject 上的 `setup` 和 `produces` | 先审批（`Reserve` 的预设回答用 `rsv-0001`，即样本里的预留），再投递 `reservation-expired.json`，期望出现 `conformance.widget.reverted.v1` |
| CP-JOBS-01 | `jobs.cron` | `widget.daily`，覆盖为 `{"cron": "@every 2s"}`；数 `daily_summary` 审计行 |
| 调和器、CP-IDEM-05 | `jobs.reconcilers` | `Reserve` 挂起超过 15 s 的路由截止时间：202 `APPROVING`；再让 `GetReservationStatus` 答已预留：部件变成 `APPROVED` |
| CP-LIFE-02 | 列表上的 `range` | `created_after`、`created_before`、`include_cold` |
| blob | `blob` | 上传 `POST /widgets/{id}/attachments`（`$.upload_url`、`$.max_bytes`），下载 `GET /widgets/{id}/attachments/{attachment_id}`（`$.download_url`） |
| 用户面 HTTP 依赖 | `dependencies` 里形如 `<METHOD> <path>` 的键 | `GET /conformance/peer/owners/{owner_id}`：假 peer 既答 gRPC 也答 HTTP |
| 样本 | 占位符 | `{id}` 是新建的部件，`{sub:<persona>}` 是该角色的 sub |

## 坏变体

以 `BROKEN=<name>` 构建，每个只违反一条规则，见 `broken-variants.yaml`：`accept-refresh`、`healthz-db`、`no-ce-id`、`select-claim`、`no-set-role`、`unbounded-pool`、`no-deadline`、`leak-internal`。

## 本处补定的口径

协议设计给 widget 的提纲之外补了这些，请评审：Public 路由 `GET /kinds` 与 Authenticated 路由 `PUT /owners/me`（每种守卫一个路由，外加个人信息日志）；字段键 `conformance.widget.price.edit`；`GET /widgets/{id}/owner`（UserHTTP）；附件路由（blob profile）；rpc `GetTouchStatus`（跨组件写都要提供）与面向用户的 `ApproveWidget`；subject `conformance.widget.reverted.v1` 与对 `conformance.reservation.expired.v1` 的订阅（一个会发布事件的 handler，一个交易单据消费者）；`mdm/org` 作为可选依赖；参考表结构 `migrations/0001_widget.sql`；只有契约的依赖 `conformance/peer`。
