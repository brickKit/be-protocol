[English](CHANGELOG.md) · [中文](CHANGELOG.zh.md)

# 变更记录

发版 tag 写成 `vMAJOR.MINOR.PATCH`；组件声明的协议版本是 `MAJOR.MINOR`（见 README 的“版本规则”）。

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
