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
