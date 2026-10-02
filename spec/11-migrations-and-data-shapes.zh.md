[English](11-migrations-and-data-shapes.md) · [中文](11-migrations-and-data-shapes.zh.md)

# P11 迁移与数据形状

迁移怎么运行、可以包含什么，运行时在组件自己的迁移之后追加的平台迁移，以及每个组件都使用的列形状：主键、金额、数量、瞬时、业务日期、法人和单据编号。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P11.1 | MUST | 迁移以属主角色 `PG_OWNER_USER`（密码 `PG_OWNER_PASSWORD`）登录，直连 PostgreSQL（设置了 `PG_MIGRATION_HOST` / `PG_MIGRATION_PORT` 时连它们）。会话参数：`lock_timeout = 5s`、`statement_timeout = 15min`。拿锁超时会退避重试，最多 3 次；最终失败时记录阻塞者后端的 pid 和它们 SQL 的前 200 个字符。迁移连接是一个专用会话：允许迁移工具在它上面设置会话级的 `search_path`、获取会话级 advisory 锁（这是 [P10.2](10-database.zh.md) 和 [P10.8](10-database.zh.md) 的例外）。迁移锁按 schema 区分：两个组件同时迁移同一个数据库，都会成功 | CP-CORE-01 |
| P11.2 | MUST | 迁移文件里不出现 `OWNER TO`、`GRANT`、`REVOKE`、`CREATE SCHEMA`、`CREATE ROLE`、`ALTER ROLE`、`SET`，不出现带 schema 限定的名字，不出现角色或 schema 字面量，也不出现以日期字面量为边界的分区。名字都不带限定，靠 `search_path` 解析 | CP-DB-01（门禁 `migration-identity-scan`） |
| P11.3 | MUST | 迁移状态表放在本组件自己的 schema 里；官方 SDK 使用[下表](#迁移状态表)里的表名，这些表不受 P11.11 约束。组件的迁移之后，在同一个迁移步骤里、以属主角色，运行时运行**平台迁移**，顺序为：建或升级 `besdk_*` 表和平台函数（[ddl/](../ddl/)），把版本记在 `besdk_platform_version`；按 `lifecycle.yaml` 为每张分区表建出当前分区窗口（[P16.6](16-data-lifecycle.zh.md)）；确保事件流和本组件的 durable 存在（[P12.4](12-events.zh.md)、[P12.5](12-events.zh.md)）。三者都幂等。`besdk_*` 表与参考 DDL 逐列一致 | CP-DB-04, CP-LIFE-01 |
| P11.4 | MUST | schema 演进遵守 expand / contract。contract 类迁移以文件头行 `-- be:contract after=<version>` 开头；`CREATE INDEX CONCURRENTLY` 单独一个文件，文件以 `-- be:no-transaction` 开头。生产只前滚 | —（门禁） |
| P11.5 | MUST | 每个自有主键都是 UUIDv7（RFC 9562），列类型 `uuid`，由应用在插入前生成，从不由列默认值生成。分区表的主键是 `(id, created_at)`，`created_at` 等于 id 里内嵌的时间戳。对另一个组件记录的引用是 `TEXT`，不加外键。线上 id 是不透明字符串，采用 36 字符小写的规范形式。例外：严格单调的计数器用 `BIGINT GENERATED ALWAYS AS IDENTITY`；以标准代码为键的参考表（币种、单位）用该代码作键，类型 `TEXT` | CP-DB-01（门禁 `id-type-scan`） |
| P11.6 | MUST | 列形状：金额 `NUMERIC(19,4)`；单价、成本和数量 `NUMERIC(19,6)`；汇率 `NUMERIC(19,10)`；比率（折扣、税率）`NUMERIC(9,6)`；单位换算系数 `NUMERIC(24,12)`；币种 `CHAR(3)`（ISO 4217 字母代码，大写）。金额在其单据上总是与币种成对出现。舍入只在运行时的 money 实现里做，按币种的 ISO 4217 小数位，默认 `HALF_AWAY_FROM_ZERO`（可要求 `HALF_EVEN`）；分摊用最大余数法。线上的金额、价格、数量、汇率和比率都是十进制字符串：可选的 `-`、数字、可选的 `.` 和数字；没有指数、没有 `+`、没有分隔符、没有 `NaN`；其它任何形式都是 `INVALID_ARGUMENT` | —（向量 `money`） |
| P11.7 | MUST | 瞬时用 `timestamptz`，以带 `Z` 的 RFC 3339 UTC 发送。业务日期用 `DATE`，以 `YYYY-MM-DD` 发送，按**法人**的业务时区计算。SQL 里从不使用 `CURRENT_DATE`、`now()::date`、`date_trunc(…, now())`，也不对 `timestamptz` 用 `::date`："今天"和每一个日期边界都由运行时算出，作为参数传入。`DATE` 只和 `DATE` 比较。事件带上其单据的业务日期。运行时自带 IANA 时区数据库（Go `time/tzdata`、Python 的 `tzdata` 包、带完整 ICU 的 Node），从不依赖镜像里的 `/usr/share/zoneinfo`；它在 `/_be/info`（`tzdata`）里报告版本，这个版本一变就重跑日历向量 | —（门禁 `business-date-scan`，向量 `calendar`） |
| P11.8 | MUST | 每张交易单据表都有 `legal_entity_id TEXT NOT NULL`；每个关于交易单据的事件都在 payload 里带 `legal_entity_id`，在信封里带 `ce-legalentity`。这类事件缺法人时，消费者把它送进死信；从不把它记到默认法人上 | CP-EVS-07 |
| P11.9 | MUST | 法人日历（业务时区、会计年度起始月、本位币）来自 `mdm/org`，通过快照（[P15](15-snapshots.zh.md)）保存在本地；汇率来自 `mdm/currency`。没有用于法人的共享配置变量，也没有固定汇率。没装 `mdm/org` 时（没有 `MDM_ORG_ENDPOINT`，[P2.5](02-configuration.zh.md)），运行时的日历进入**降级模式**：每个法人都用 `BUSINESS_TIMEZONE`、会计年度起始月 1，并以自己的 id 作为 `{le}` 代码；`/_be/info` 在 `degraded` 里列出 `calendar`（[P20](20-self-description-and-versioning.zh.md)）。是否降级在启动时按配置决定，从不按调用决定 | — |
| P11.10 | MUST | 单据编号来自 `besdk_number_series` 表（[ddl/](../ddl/)），键为 `(series, scope, period)`。**无缺号**序列（`gapless = true`，会计凭证）在与单据相同的事务里锁住它的行，因此期间内编号连续，回滚会退回编号；编号只在幂等认领成功之后才分配。其它序列在自己的一个短事务里预留号段，可以有缺号，但从不重复。格式是组件的配置键 `<SERIES>_NO_FORMAT`，占位符为 `{le}`、`{yyyy}`、`{yy}`、`{mm}`、`{seq:N}`；格式里的日期是业务日期。唯一性由不分区的平台表 `besdk_number_allocations` 保证，主键 `(legal_entity_id, series, number)`（[ddl/](../ddl/)）：运行时在单据自己的事务里把每个格式化后的编号插进这张表，所以重复会让该事务在这张表上以 SQLSTATE `23505` 失败（序列配置错误，以 `INTERNAL` 暴露），回滚会把编号放回去。单据表自己的唯一约束不是这个机制：分区表上的唯一索引必须包含分区键，所以 `(legal_entity_id, number)` 没法跨分区唯一 | —（向量 `numbering`） |
| P11.11 | MUST | 组件迁移创建的每张表都在 `migrations/lifecycle.yaml` 里声明（[P16.1](16-data-lifecycle.zh.md)）。`besdk_*` 表和官方的迁移状态表不受此约束；运行时不是官方 SDK 的组件，把它的迁移工具的状态表声明为 `class: platform`。迁移目录里只放 `*.sql` 文件和 `lifecycle.yaml` | CP-LIFE-04 |

## 列形状

| 什么 | 列 | 线上 |
|---|---|---|
| 自有 id | `uuid`（UUIDv7） | 字符串，36 字符，小写 |
| 对另一个组件 id 的引用 | `TEXT` | 不透明字符串 |
| 瞬时 | `timestamptz` | RFC 3339 UTC，`Z` |
| 业务日期 | `DATE` | `YYYY-MM-DD` |
| 金额 | `NUMERIC(19,4)` + `currency CHAR(3)` | 按币种小数位的十进制字符串，外加 `currency` |
| 本位币金额 | `NUMERIC(19,4)` | 十进制字符串 |
| 单价、成本、数量 | `NUMERIC(19,6)` | 十进制字符串，最多 6 位小数 |
| 汇率 | `NUMERIC(19,10)`，带 `fx_rate_date DATE`、`fx_rate_type TEXT` | 十进制字符串，最多 10 位小数 |
| 比率 | `NUMERIC(9,6)` | 十进制字符串，`0.130000` = 13 % |
| 换算系数 | `NUMERIC(24,12)` | 十进制字符串 |
| 法人 | `legal_entity_id TEXT NOT NULL` | 字符串 |

## 迁移文件头

| 文件头（第一行） | 含义 |
|---|---|
| `-- be:no-transaction` | 文件在事务外运行（只用于单独一个的 `CREATE INDEX CONCURRENTLY`） |
| `-- be:contract after=<version>` | contract 步骤；只在每个正在运行的版本都至少是 `<version>` 时才运行 |

## 迁移状态表

| 运行时 | 组件迁移 | 平台迁移 | 迁移锁（按 schema，会等待） | 谁跳过 `lifecycle.yaml` |
|---|---|---|---|---|
| be-sdk-go (golang-migrate) | `schema_migrations_<PG_SCHEMA>` | `besdk_migrations_<PG_SCHEMA>` | 工具的会话级 advisory 锁，id 由数据库、schema 和状态表推出 | 源只读 `<version>_<name>.up.sql` / `.down.sql` |
| be-sdk-python (yoyo) | `_yoyo_migration`, `_yoyo_log`, `_yoyo_version`, `yoyo_lock` | 同样这些表；平台迁移的 id 以 `besdk-` 开头 | 本 schema 的 `yoyo_lock` 里的那一行 | 工具只读 `*.sql` 和 `*.py` |
| be-sdk-ts (node-pg-migrate) | `pgmigrations_<PG_SCHEMA>` | `besdk_migrations_<PG_SCHEMA>` | 工具的 advisory 锁，`lockValue` 由 `PG_SCHEMA` 推出（用它的常量默认值会让所有 schema 共用一把锁）；工具自己拿不到锁会立刻失败，所以运行时重试到拿到为止 | 只放行 `*.sql` 的 `ignorePattern` |

其它语言的运行时把自己工具的表声明为 `class: platform`（P11.11），并在 `AGENTS.md` 里写明它的锁；锁**必须**按 schema（P11.1）。

## 说明

- 平台迁移的 DDL 是规范性的：套件把迁移后 schema 的系统目录与 [ddl/](../ddl/) 比较（`CP-DB-04`）。
- 列的 scale 是它的容量，不是它的精度：存入的值已经按币种或单位允许的位数舍入过。
