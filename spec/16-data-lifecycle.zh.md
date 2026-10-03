[English](16-data-lifecycle.md) · [中文](16-data-lifecycle.zh.md)

# P16 数据生命周期

组件拥有的每一张表怎么分类、分区、封存、冷冻、保留和销毁：声明文件 `migrations/lifecycle.yaml` v1、引擎的保证、时间范围的读取契约，以及资源契约 `_lifecycle/*`。Schema：[`lifecycle.schema.json`](../schemas/lifecycle.schema.json)、[`data-lifecycle-config.schema.json`](../schemas/data-lifecycle-config.schema.json)；表：`besdk_lifecycle_units`、`besdk_lifecycle_log`、`besdk_holds`、`besdk_erasures`、`besdk_exports`（[ddl/](../ddl/)）；REST [`openapi/resource-lifecycle.yaml`](../openapi/resource-lifecycle.yaml)；gRPC [`proto/be/lifecycle/v1/lifecycle.proto`](../proto/be/lifecycle/v1/lifecycle.proto)。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P16.1 | MUST | 每个有数据库的组件都提供 `migrations/lifecycle.yaml` v1，和它的迁移一起嵌入。它的迁移创建的每一张表都要声明。不变式在加载声明时检查（违反即致命，并点名是哪张表）：`ledger` 表没有 `pii` 列，也没有 `erasure.columns`；`queue` 表不声明 `tiers.cold`；`snapshot` 表不声明 `retention.min`；声明了 `tiers.cold` 的表，每个 `NUMERIC` 列都有精度；声明了 `tiers.cold`、且擦除动作不是 `restrict` 的表，不能用 WORM 冷存储（门禁 `lifecycle-scan`） | CP-LIFE-04 |
| P16.2 | MUST，INTERNAL | 引擎作为 singleton 作业 `be.lifecycle` 运行。每一步是一个事务，带一把步骤锁（[P10.8](10-database.zh.md)）和 `lock_timeout`。运行期角色没有 DDL 权限（[P10.12](10-database.zh.md)）：运行期里，引擎只通过平台的 `SECURITY DEFINER` 函数提前建分区、装封存守卫、删除到期的 platform 和 queue 分区（在短 `lock_timeout` 下做普通的 `DETACH`），以及解冻冷单元：解冻先建出该单元的表、不挂上（`besdk_thaw_create`），用普通 `INSERT` 灌回它的行，再封存并挂上（`besdk_thaw_attach`）；解冻单元重新冷冻时用 `besdk_drop_partition` 删掉，冷副本保留。`DETACH PARTITION … CONCURRENTLY` 不能在函数或事务块里运行，所以已冷冻业务单元的 detach 和 drop 在迁移步骤里执行，以属主角色身份，在它的专用连接上。引擎守住下面的保证 G1–G12 | —（生命周期套件） |
| P16.3 | MUST | 读一个时间范围，要么返回完整结果，要么答 `400` `FAILED_PRECONDITION`，reason 为 `RANGE_COLD`，`metadata` 为 `{online_from, cold_ranges, thaw_allowed, export_allowed}`（`cold_ranges` 是 `<from>/<to>` 对，逗号分隔）。从不静默截断。`List` 请求接受可选的布尔字段 `include_cold`（默认 false）。不带时间范围的列表请求，按表的 `tiers.hot` 窗口过滤（`none` = 没有窗口）；这是默认过滤，不是上限：比窗口更旧、但仍在线（温层）的行，在请求指定了覆盖它们的范围时会返回 | CP-LIFE-02 |
| P16.4 | MUST | 资源契约 `/{domain}/{name}/_lifecycle/*` 和 gRPC `be.lifecycle.v1.Lifecycle` 全部挂出；还没实现的端点答 `501` `CAPABILITY_UNAVAILABLE`，并带 `metadata.capability` | CP-LIFE-03 |
| P16.5 | MUST | 封存单元不可改：`UPDATE`、`DELETE` 和 `TRUNCATE` 被调用平台函数 `besdk_sealed_guard()`（[ddl/](../ddl/)）的触发器拒绝，该函数抛出 SQLSTATE `BE001`；运行时把它映射成 `FAILED_PRECONDITION` / `UNIT_SEALED`。`besdk_lifecycle_log` 从创建起就带同样的守卫 | — |
| P16.6 | MUST | 任何一天迁移的数据库，当天就能写入：平台迁移建好当前的分区窗口（[P11.3](11-migrations-and-data-shapes.zh.md)）；运行期窗口始终覆盖 `ahead` | CP-LIFE-01 |
| P16.7 | MUST | 引擎的每个动作都向 `besdk_lifecycle_log` 追加一行（追加型，永久保留），并通过 outbox 发布 `<domain>.<name>.lifecycle.<action>.v1`，`<action>` 是 `sealed`、`frozen`、`thawed`、`destroyed`、`erasure_completed` 之一 | — |
| P16.8 | MUST | 每个组件有三个权限键保护资源契约，由项目的工具登记：`<domain>.<name>.lifecycle.read`（单元、导出）、`<domain>.<name>.lifecycle.thaw`、`<domain>.<name>.lifecycle.admin`（保全、擦除、销毁审批） | CP-LIFE-03 |
| P16.9 | MUST | `DATA_LIFECYCLE` 选择模式（`on`、`dry-run`、`off`）和适配器；运行时没有的适配器会让启动失败，并点名是哪一个（[P1.8](01-process-and-lifecycle.zh.md)）。逐表覆盖只能延长 `retention.min`；低于声明下限的覆盖会让启动失败。YAML 值按 YAML 1.2 core schema 读取，其中 `on` 和 `off` 是字符串；写的一方要给它们加引号（`mode: "on"`），因为 YAML 1.1 的解析器会把它们读成布尔值 | — |
| P16.10 | MUST | 运行时建的范围分区（平台的，以及 `lifecycle.yaml` 用 `grain` 声明的）按下界命名：`grain` 为 `week` 时是 `<parent>_<ISO 周年>w<WW>`（`besdk_outbox_2026w40`，ISO 8601 周，从周一 00:00 UTC 开始），`month` 是 `<parent>_<YYYY>m<MM>`，`year` 是 `<parent>_<YYYY>`；边界为 UTC 的 `[start, end)`。这个名字就是 `besdk_lifecycle_units` 里的单元键，所以每个运行时规划出的单元相同（G12） | CP-LIFE-01 |

## 表的类别

| 类别 | 是什么 | 分区 | 封存 | 冷层 | 到期 |
|---|---|---|---|---|---|
| `master` | 可变的主数据，量有上界 | 否 | 否 | 否 | 保留；擦除时把个人信息列匿名化 |
| `reference` | 配置、字典、模板 | 否 | 否 | 否 | 保留；没有个人数据 |
| `document` | 有状态机的业务单据 | 按创建时间（建议）或行单元 | 关闭后满 N 个月 | 可选 | 按保留期 |
| `ledger` | 追加型账簿 | 按时间或期间 | `immediate` 或 `on_signal` | 可选，在结转之后 | 法定下限，到期后审批 |
| `audit` | 谁在何时做了什么 | 按时间 | `immediate` | 可选 | ≥ 6 个月，默认 3 年 |
| `queue` | 有未结束状态的工作项 | 按时间 | 否 | 从不 | 没有未结束行时删除 |
| `snapshot` | 本地副本，可重建 | 任意 | 否 | 从不 | 随时 |
| `platform` | 运行时自有（`besdk_*`） | 运行时 | — | 从不 | 运行时（outbox 发布后 14 天；游标和幂等 30 天；队列里 `done` 的行 7 天；作业时间槽 30 天） |

## 单元状态

`ACTIVE` → `SEALED` → `EXPORTING` → `EXPORTED` → `VERIFIED` → `COLD_PENDING_DROP` → `COLD` → `DESTROYED`；封存检查失败时为 `BLOCKED`；冷单元以只读方式重新挂载期间为 `THAWED`。每个单元的状态在 `besdk_lifecycle_units.state` 里；崩溃之后引擎从它接着做。

## 保证

| # | 保证 |
|---|---|
| G1 | 任何日期跑的迁移，当天就能写入；窗口始终覆盖 `ahead` |
| G2 | 同一 schema 的同一步，同一时刻只有一个执行者；不同 schema 互不阻塞；DDL 从不在热路径上排队 |
| G3 | 没有任何行会在它声明的 `retention.min` 之前被删除 |
| G4 | `document`、`ledger` 或 `audit` 类的数据，只有在已校验的冷副本存在之后才离开数据库；冷存储为 `none` 时跳过冷冻，数据留在温层 |
| G5 | 封存单元不可改（`UNIT_SEALED`） |
| G6 | 封存单元的摘要链随时可以校验（`GET _lifecycle/verify`） |
| G7 | 时间范围的读取要么完整，要么答 `RANGE_COLD` |
| G8 | 冷读取套用与热读取相同的数据范围谓词；表达不了某个谓词的适配器拒绝，而不是放宽 |
| G9 | 保全之下的数据从不被销毁或擦除；冷冻它仍然允许（数据仍被保存） |
| G10 | 擦除作用于每一层，并留下回执；时间点恢复之后会重放 |
| G11 | 每个动作都记在 `besdk_lifecycle_log` 里，并以事件公告 |
| G12 | 对同样的输入，每个官方 SDK 的 planner 给出逐项完全相同的动作序列（一致性向量 `lifecycle`） |

## 单元的规范摘要

每一行按声明的顺序逐列编码，每个值用 PostgreSQL 的文本输出格式，NULL 写成 `\N`；字段之间用 `0x1F` 分隔，行之间用 `0x1E` 分隔，行按主键排序；单元摘要是整体的 SHA-256。链是 `chain_n = SHA-256(chain_{n-1} ‖ unit_digest_n)`。导出、校验和解冻都用同样的方法计算，所以任何工具都能独立核对。

## 说明

- 冷存储和冷查询适配器是由 `DATA_LIFECYCLE` 选择的 SDK 适配器；两者都为 `none` 时（1.0 的默认值），引擎只保留热层和温层，并且从不答 `RANGE_COLD`，因为没有任何数据被冷冻。
- 法定最低保留期是一个下限，部署只能调高它。
