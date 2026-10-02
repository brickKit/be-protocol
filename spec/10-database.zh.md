[English](10-database.md) · [中文](10-database.zh.md)

# P10 数据库：身份、事务、池

组件的每一次数据库访问在线上对 PostgreSQL 做什么：用哪个角色和 schema、每个事务开头的语句、隔离级别与重试、SQLSTATE 怎样离开事务、池上限、启动探测、advisory 锁和原子认领。单跑组件的引擎是 PostgreSQL ≥ 14；外壳因为要用 NOINHERIT 授权，需要 PostgreSQL ≥ 16（[P19.5](19-shells.zh.md)）。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P10.1 | MUST | 数据库身份只来自配置，分成两个独立的角色和一个 schema：**属主角色** `PG_OWNER_USER` 拥有组件的表并执行它的 DDL（只在迁移时）；**运行期角色** `PG_USER` 只有 DML，不是属主角色的成员，是每个运行期事务都要切换到的角色；`PG_SCHEMA` 是 schema。三者都必填，没有默认值，从不互相推导，也从不由组件 ID 推导。代码、迁移和测试夹具里不出现派生名（`_rw`、`_archive`、`shell_`），也不出现本组件自己的 schema 或角色字面量。组件代码自己从不发出 `SET ROLE` 或 `SET LOCAL ROLE`：只有运行时的存储层会发（门禁 `identity-literal-scan`） | CP-DB-01 |
| P10.2 | MUST，INTERNAL | 每一次数据库访问都在一个以 `SET LOCAL ROLE <PG_USER>`、`SET LOCAL search_path TO <PG_SCHEMA>` 和 `SET LOCAL application_name = '<component ID>'`（在外壳里是成员的 ID）开头的事务里运行：业务事务、outbox 泵、消费者、job、生命周期引擎、投影拉取和启动探测，没有例外。`search_path` 只放本组件的 schema。在池里的连接上从不发出会话级的 `SET`。唯一的例外是专用的、不进池的迁移连接（[P11.1](11-migrations-and-data-shapes.zh.md)）：它以属主角色登录，它的工具可以设置会话级的 `search_path`、获取会话级 advisory 锁，用完即关闭。它是唯一直接执行 DDL 的连接。运行时为某个成员发出的每条语句都以注释 `/* be:<PG_SCHEMA> */` 开头，这样驱动按 SQL 文本做键的每连接预编译语句缓存（pgx、asyncpg）在共享的物理连接上，永远不会把为另一个成员的 schema 预编译的语句交给这个成员；预编译语句按名字区分的驱动（node-postgres）要么只用不具名语句，要么把成员的 schema 放进名字里 | CP-DB-01, CP-SHELL-07 |
| P10.3 | MUST | 每个事务都用 `SET LOCAL` 设置：`statement_timeout = min(5 s, remaining deadline)`、`lock_timeout = 2 s`、`idle_in_transaction_session_timeout = 30 s`；PostgreSQL ≥ 17 时再设 `transaction_timeout = remaining deadline`。读快照（`REPEATABLE READ READ ONLY`）允许 `statement_timeout` 最高到 30 s。会话 `TimeZone` 是 UTC，从不更改 | CP-DB-02 |
| P10.4 | MUST | 隔离级别默认 `READ COMMITTED`；事务可以要求 `REPEATABLE READ` 或 `SERIALIZABLE`。SQLSTATE 按[下表](#sqlstate-映射)离开事务：`40001` 和 `40P01` 回滚并重新执行整个事务体，最多 3 次尝试，间隔 `10 ms · 2^n` ± 抖动，之后为 `ABORTED` / `TX_CONFLICT`；`55P03` → `ABORTED` / `LOCK_TIMEOUT`；`57014` 和 `25P04` → `DEADLINE_EXCEEDED` / `STATEMENT_TIMEOUT`；`53300` → `UNAVAILABLE` / `DB_TOO_MANY_CONNECTIONS`。重试计入 `be_tx_retries_total{reason}` | CP-DB-02 |
| P10.5 | MUST | 池。单跑：最多 `PG_POOL_MAX` 条连接。外壳里：一个物理池，`min(Σ members' PG_POOL_MAX, the shell's PG_POOL_MAX)` 条连接，每个成员再限制为它自己 `PG_POOL_MAX` 条并发连接。取不到连接的工作单元最多等待 `min(PG_POOL_ACQUIRE_TIMEOUT, remaining deadline)`，然后以 `RESOURCE_EXHAUSTED` / `DB_POOL_EXHAUSTED` 失败。一个成员耗尽自己的预算，从不影响另一个成员。成员的连接在 `pg_stat_activity` 里按 `application_name`（P10.2）计数，不按 `usename` 计数，后者在外壳里总是外壳的登录角色。连接在 `PG_CONN_MAX_LIFETIME` 之后替换，空闲 `PG_CONN_MAX_IDLE_TIME` 之后关闭 | CP-DB-03, CP-SHELL-05 |
| P10.6 | INTERNAL | 一个工作单元同一时刻最多持有一条连接：已经在事务里时再开事务会被拒绝（这是编程错误，reason 为 `NESTED_TX`，以通用的 `INTERNAL` 回答，[P4.3](04-errors.zh.md)）。在本地写入的事件 handler 拿到的是消费者的事务，而不是自己再开一个 | — |
| P10.7 | MUST | 启动探测，在后台运行，从不属于 `/healthz`。**能力**：`server_version_num ≥ 140000`（外壳里 ≥ 160000）、声明式分区、`FOR UPDATE SKIP LOCKED`；缺少某项能力是致命的，并指出缺的是哪项（[P1.8](01-process-and-lifecycle.zh.md)）。**身份**，在以 `PG_USER` 运行的事务里检查：`has_schema_privilege(current_user, current_schema(), 'USAGE')` 为真，`… 'CREATE'` 为假；`pg_has_role(current_user, <PG_OWNER_USER>, 'MEMBER')` 为假；schema 里的每张表都属于 `PG_OWNER_USER`，且 `PG_USER` 对每张表都有 `SELECT, INSERT, UPDATE, DELETE`；失败时记 ERROR 日志，导出 `be_db_identity_ok = 0`，并让 `/readyz` 答 `503`，但不结束进程 | CP-DB-01, CP-CORE-05 |
| P10.8 | MUST，INTERNAL | advisory 锁只用事务级的：`pg_advisory_xact_lock(hashtext(current_schema() \|\| ':' \|\| <name>), hashtext(<parts joined by '\|'>))`，或用同一个键的 `pg_try_advisory_xact_lock`。两个外壳成员用同一个锁名时从不相撞；一个组件同时以单跑和外壳方式运行、共用一个 schema 时，自己与自己互斥。在池里的连接上从不获取会话级 advisory 锁（迁移连接上的工具锁是例外，[P11.1](11-migrations-and-data-shapes.zh.md)） | CP-JOBS-02 |
| P10.9 | MUST | 对队列行或幂等键的认领是原子的：`FOR UPDATE SKIP LOCKED`，或 `INSERT … ON CONFLICT DO NOTHING` / `DO UPDATE … WHERE … RETURNING`。从不用普通 `SELECT` 加随后的写入来认领 | CP-EVP-03, CP-IDEM-07 |
| P10.10 | MUST（组件义务） | 锁多行的事务，按主键或业务键的固定顺序加锁（例如同一个预留的多条库存行，按 `(warehouse_id, product_id)`） | —（INTERNAL） |
| P10.11 | MUST | 连接池代理（pooler）是可选的。使用时只用 transaction 模式。PgBouncer ≥ 1.21 且 `max_prepared_statements > 0` 时，驱动的语句缓存可以保持开启；用其它任何 pooler 时都关闭它。迁移通过 `PG_MIGRATION_HOST` / `PG_MIGRATION_PORT` 直连 | — |
| P10.12 | MUST，部分 INTERNAL | 运行中的服务从不以 `PG_OWNER_USER` 登录。brickKit 给迁移容器的环境与服务完全相同，所以服务也会收到 `PG_OWNER_USER` / `PG_OWNER_PASSWORD`；运行时不得使用它们（这是写进文档的限制，直到 brickKit 能给迁移步骤单独的变量）。服务运行期间生命周期引擎需要的 DDL（提前建分区、安装封存守卫、删除过期的平台分区或队列分区、解冻冷单元）只经平台的 `SECURITY DEFINER` 函数执行（[ddl/10-lifecycle-functions.sql](../ddl/10-lifecycle-functions.sql)），这些函数由属主在平台迁移中创建 | CP-DB-05 |

## 每个事务发出的语句

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;            -- or the level the transaction asked for
SET LOCAL ROLE <PG_USER>;                        -- in a shell: the member's own PG_USER
SET LOCAL search_path TO <PG_SCHEMA>;
SET LOCAL application_name = '<component ID>';  -- in a shell: the member's ID
SET LOCAL statement_timeout = '<min(5s, remaining)>';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
SET LOCAL transaction_timeout = '<remaining>';   -- PostgreSQL 17 or later only
/* be:<PG_SCHEMA> */ SELECT …                    -- 事务体；每条语句都带成员的前缀
COMMIT;
```

角色名和 schema 名按 SQL 标识符加引号。对登录角色做 `ALTER ROLE … SET`，是给绕过运行时的会话（psql、脚本）的兜底；它不是机制本身，因为 `SET ROLE` 之后，目标角色的设置不生效。

## SQLSTATE 映射

| SQLSTATE | 含义 | 运行时动作 | 表现为（code / reason） |
|---|---|---|---|
| `40001` | 序列化失败 | 重试事务体，最多 3 次尝试 | 最后一次之后：`ABORTED` / `TX_CONFLICT` |
| `40P01` | 死锁 | 同上 | 同上 |
| `55P03` | 锁不可用 | 不重试 | `ABORTED` / `LOCK_TIMEOUT` |
| `57014` | 语句被取消 | 不重试 | `DEADLINE_EXCEEDED` / `STATEMENT_TIMEOUT` |
| `25P04` | 事务超时（17+） | 不重试 | `DEADLINE_EXCEEDED` / `STATEMENT_TIMEOUT` |
| `25P03` | 事务内空闲过久 | 服务端关闭连接 | `INTERNAL`（组件 bug） |
| `53300` | 连接过多 | 不重试 | `UNAVAILABLE` / `DB_TOO_MANY_CONNECTIONS` |
| `23505` | 唯一约束冲突 | 不重试 | 组件把它映射成自己的 reason，通常是 `ALREADY_EXISTS` |
| `BE001` | 由触发器函数 `besdk_sealed_guard` 抛出：写入已封存的单元（[P16.5](16-data-lifecycle.zh.md)） | 不重试 | `FAILED_PRECONDITION` / `UNIT_SEALED` |

## 角色

| 角色 | 登录 | 拥有 | 使用者 |
|---|---|---|---|
| `PG_OWNER_USER` | 是 | `PG_SCHEMA` 里的表、序列和函数，因为迁移和平台迁移以这个角色运行 | 只有迁移步骤 |
| `PG_USER` | 是 | 无；对 `PG_SCHEMA` 有 `USAGE`，通过默认权限对其中的表有 DML；不是属主角色的成员 | 运行中的服务（单跑时是它的登录角色） |
| 外壳登录角色 | 是 | 无 | 外壳；被授予它承载的每个成员的 `PG_USER`（从不授予属主角色），带 `INHERIT FALSE, SET TRUE`（[P19.5](19-shells.zh.md)） |

角色、授权、默认权限（`ALTER DEFAULT PRIVILEGES FOR ROLE <owner> IN SCHEMA <schema> GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES` 和 `USAGE, SELECT ON SEQUENCES`，授予运行期角色）以及兜底用的角色设置，由项目的数据库初始化创建，从不由迁移创建（[P11.2](11-migrations-and-data-shapes.zh.md)）。

## 说明

- 不带 `LOCAL` 时，设置会比事务活得更久，池里这条连接的下一个借用者就在另一个 schema 里运行，没有任何报错。
- 每事务超时才是保证，因为外壳以自己的角色登录，所以成员角色的 `ALTER ROLE … SET` 在外壳里从不生效。
