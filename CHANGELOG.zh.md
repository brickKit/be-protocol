[English](CHANGELOG.md) · [中文](CHANGELOG.zh.md)

# 变更记录

发版 tag 写成 `vMAJOR.MINOR.PATCH`；组件声明的协议版本是 `MAJOR.MINOR`（见 README 的“版本规则”）。

## v1.0.0-rc.2

第一批 SDK、套件和 be-ops 通道（阶段 B 第一波）的裁决，在试点组件之前落地。要求 brickKit ≥ v1.4.0。

- **`be` 域的 reason**：36 个（原 33 个）。新增 `REQUEST_INVALID`（`INVALID_ARGUMENT`，400：请求解不开或不符合 schema）、`DEPENDENCY_UNAVAILABLE`（`UNAVAILABLE`，503，`metadata.dependency` = `db`、`bus`、`blob` 或组件 / 族 ID；SQLSTATE `08` 类、`57P01`–`57P03`）、`REQUEST_CANCELLED`（`CANCELLED`，499：运行时回答的每个错误现在都带 reason）。访问日志行的级别按响应的 code 定（P4.6）。
- **路由判定顺序**：验 token（401）→ 还没有 bundle → 每个非 Public 路由答 `503`（含 Authenticated）→ token 过期或授权被撤销（`TOKEN_STALE`）→ 沿 `act` 链检查代理能力，含 `impersonation`（`UNSUPPORTED_DELEGATION`）→ Authenticated → 键。`413` 可以先于守卫。
- **配置**：空值对所有类型都算没设；布尔为 `true`、`false`、`1`、`0`；`one_of` = 至少设一个；`EVENTS_MAX_DELIVER` / `EVENTS_BACKOFF` 目录里没有默认值（用订阅自己的值）；删除 `PG_POOL_MIN_IDLE`；新增 `DEPLOY_ENV`；`DEFAULT_LOCALE` 不是 `zh` / `en` 时退回 `en`；没有 `COMPONENT_ID` 以 64 退出；profile 触发键（`db`：`PG_SCHEMA` 或 `PG_HOST`；`blob`：`S3_BUCKET` 或 `S3_URL`）；目录字段 `shell: process | member`。
- **OpenAPI 标记**：每个 operation 声明 `x-be-permission`；没写的一律失败即关闭，除非标了 `x-be-internal: true`（provider 面、运维端点；从不路由，不受边缘覆盖检查）。`openapi/ops.yaml` 的运维端点带上了它；widget 的 OpenAPI 带上 be-ops 生成的资源契约区段。
- **数据库与迁移**：`PG_SCHEMA` ≤ 40 个字符；会话级 `application_name` `<component ID>@<version>`，每个成员始终保留一个会话（外壳里是在场会话）；`-- be:contract after=<version>` 在还有该版本或更旧版本的会话连着时让迁移以 1 退出；能力探测只看 `server_version_num`；记录阻塞者时查询文本看得见才记；`be_tx_retries_total{sqlstate}`；授权投影只建在声明了 `resources` 的 schema 里。
- **事件**：payload 超过 64 KiB 在发布时拒收；最后一次允许的投递失败照常 nak，消息在下一次到达时进死信；订阅的聚合类型可选，缺省用 `ce-aggregatetype`；事件契约里用 `x-signal: true` 标 poke；outbox 加列 `tracestate`；分区命名 `<parent>_<ISO 周年>w<WW>` / `m<MM>` / `<YYYY>`（P16.10）；PostgreSQL 队列适配器用组件的 `PG_USER`，分区经 `be_bus_owner` 所有的 `SECURITY DEFINER` 函数维护，并有 DEFAULT 分区；没有适配器的总线 scheme 让启动失败。
- **可观测性**：`service.namespace` = 领域，`deployment.environment.name` = `DEPLOY_ENV`；不采样的 `traceparent` 照常传播、不记录；日志行 ≤ 2048 字节（含换行），列出信封字段；访问日志只管用户面和资源契约。
- **默认保留期**：队列里 `done` 的行 7 天，作业时间槽 30 天（outbox 14 天，游标和幂等 30 天）。
- **系统面**：面向用户的 rpc 答 `TOKEN_INVALID`；被身份检查或批量上限拒绝的调用也被追踪和计数（拦截器顺序变了）；剩余 ≤ 50 ms 不发出；`map` 字段不算批量。
- **自描述与发版**：`/_be/info` 的 `profiles` 必须等于选出的那一组；`release: {checks: [[make, conformance]]}`（P20.5）；`compconf-record-scan` 只管没声明这项检查的组件；用例可以带 `applies_when`（CP-ERR-02、CP-ERR-03），报告可以写 `not_applicable`；夹具新增 `config` 和 `paired_with`。Docker Engine 29 上 Traefik ≥ 3.6。
  - 改动的要求：P1.2、P1.5、P2.3、P2.8、P3.6、P3.10、P4.1、P4.6、P5.4、P5.5、P5.6、P6.2、P7.3、P7.4、P7.7、P7.10、P10.1、P10.2、P10.4、P10.5、P10.7、P11.1、P11.3、P11.4、P12.2、P12.6、P12.7、P12.10、P12.12、P12.16、P14.7、P18.1、P18.2、P18.4、P19.3、P20.4。新增：P3.16、P16.10、P20.5。
  - 向量（共 981 条）：`errors`（三个 reason、连接丢失的 SQLSTATE、`REQUEST_CANCELLED`、操作 `access_log_level`），`config`（`empty-string-is-value` 换成 `empty-string-is-absent`，另加 `empty-string-required`、`empty-string-optional`），`envelope`（`tracestate`、`PAYLOAD_TOO_LARGE`）。
  - Schema：`errors-be`、`config-keys`（`shell`、`DEPLOY_ENV`、退役 `PG_POOL_MIN_IDLE`）、`events-contract`（`x-signal`）、`conformance-cases`（`applies_when`）、`compconf-report`（`not_applicable`）、`fixtures`（`config`、`paired_with`）。DDL：outbox 的 `tracestate`，`be_bus` 的属主角色、DEFAULT 分区和分区函数。

## v1.0.0-rc.1

协议 1.0 的第一个候选版。尚未冻结：pilot 组件在 `v1.0.0` 之前仍可能改动它。

- 规范 P1–P20（`spec/`），英文为准、附中文镜像；要求 ID `P<章>.<号>` 与用例 ID `CP-<组>-<号>` 自此固定。
- Schema（`schemas/`）：配置键清单、`be` reason 清单、错误体、事件信封、事件契约文件、access token 的 claim、`lifecycle.yaml` v1、`DATA_LIFECYCLE`、`JOBS_OVERRIDES`、`assembly.yaml` 里本协议读的键、`/_be/info`、`conformance/fixtures.yaml`、一致性用例清单和套件报告。
- 参考 DDL（`ddl/`）：全部 `besdk_*` 表和运行时用的 `SECURITY DEFINER` 函数，已在 PostgreSQL 14 和 16 上验证；PostgreSQL 队列总线适配器（`be_bus`）的参考 DDL。
- `proto/be/v1/limits.proto`（`max_items`）、`proto/be/lifecycle/v1/lifecycle.proto`；运维端点、`_authz` / `_shares` 与 `_lifecycle` 的 OpenAPI 片段。
- 语义向量（`vectors/`）与夹具组件 `conformance/widget`（`fixtures/widget/`）。
- 打 tag 之前的对账（阶段 A）：槽位族地址与推出的 gRPC 目标、族键（`IAM_URL`、`BOOTSTRAP_ADMIN_LOGIN`，P2.10、P2.11）；domain `be` 共 33 个 reason（`RATE_LIMITED`、`UPSTREAM_*`、`NETWORK_IN_TX`、`NESTED_TX`、`DB_TOO_MANY_CONNECTIONS`）；subject 分段规则与单射的 durable 名（`.` → `__`）；运行时一侧的重投与进死信、不存在才建 durable（CP-EVS-08）；`@every` 调度；规范性的脱敏规则，新增 `authorization`、`cookie`、`set_cookie`、`api_key`；`besdk_number_allocations`；经 `SECURITY DEFINER` 函数解冻；语句前缀 `/* be:<schema> */`；日历降级模式与 `/_be/info` 里的内置时区数据；夹具为套件需要的每个事实都有了字段；`make check`。向量用例 ID `envelope.cursor.last-delivery` 和 `envelope.cursor.conformance-last` 改为 `last-allowed-failure` 和 `conformance-last-allowed`（含义变了；旧 ID 下从未发布过任何东西）。
- 打 tag 之前吸收 brickKit v1.2–v1.3.1（要求 brickKit ≥ v1.3.1）。**族地址**改成在 `config/vars.yaml` 里用 `$endpoint:` 填写的显式键：`AUTHZ_URL`、新增 `AUTHZ_GRPC_URL`、`IAM_URL`（现在 `auth` 必填）、新增 `IAM_GRPC_URL`；推算的 gRPC 目标（端口 + 1000）取消，`IAM_JWKS_URL` 退役（`{IAM_URL}/.well-known/jwks.json`）。**密钥以文件交付**：每个 `secret: true` 的键都是 `mount: file`、名字是 `…_FILE`（`PG_PASSWORD_FILE`、`PG_OWNER_PASSWORD_FILE`、`S3_ACCESS_KEY_ID_FILE`、`S3_SECRET_ACCESS_KEY_FILE`；旧名字退役），30 秒内重读，去掉一个末尾换行；运行期的 `@file:` 写法取消；指标 `be_secret_reload_failures_total`。**就绪** `/readyz` 改为 MUST、一旦满足就保持，声明为 `readinessCheck`。**停机宽限**：声明 `deployment.stopGracePeriodSeconds`（30），`SHUTDOWN_GRACE` 默认 25 秒，外壳至少取成员的值。**端口**声明 `protocol`（`http`、`grpc`），同时监听 IPv4 和 IPv6。**事件**在 `component.yaml` 的 `events` 里声明，由 be-ops 生成。**作业**：可选的 `job run <name>`，走同一批租约表和时间槽表（`/_be/info` 的 `capabilities: [job_run]`），用法错误退出码 64。`PG_MIGRATION_HOST` / `PG_MIGRATION_PORT` 退回 `PG_HOST` / `PG_PORT`；`configSchema` 的协议段由 be-ops 生成（门禁 `protocol-config-scan`）；边缘路由以路径段为界；外壳成员可以 `expose`。
  - 改动的要求：P1.1、P1.4（SHOULD → MUST）、P1.6、P2.5、P2.6、P2.7、P2.8、P2.9、P2.10、P5.4、P6.10、P7.6、P10.12、P11.1、P14.5、P17.1、P19.3。新增：P1.11、P1.12、P1.13、P2.12、P7.14、P12.16、P14.8、P19.9、P19.10。
  - 用例：CP-CORE-05 改为 MUST；新增 CP-CORE-12、CP-CORE-13、CP-CORE-14、CP-DB-06、CP-EVP-06、CP-EVS-09、CP-JOBS-06、CP-SHELL-11。profile `events-pub` 和 `events-sub` 改由 `component.yaml` 的 `events` 选定。
  - Schema：`config-keys`（`mount`、`secrets`、gRPC 族键的 `applies_when`、退役名）、`info`（`capabilities`）、`fixtures`（事件与作业的说明）。向量 `config`：`family_url` 换成 `family_address`；新操作 `secret_text`、`key_declaration`；`$endpoint:` 取值写法（196 条，合计 946 条）。夹具：`readinessCheck`、`stopGracePeriodSeconds`、端口 `protocol`、`events`、`mount: file` 密钥（`brickkit lint` v1.3.1 无错误）；新增四个故意写坏的变体。
