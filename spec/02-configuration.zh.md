[English](02-configuration.md) · [中文](02-configuration.zh.md)

# P2 配置

组件的配置从哪里来、值怎么定类型和解析，以及本协议定义的键。机器可读的目录是 [`schemas/config-keys.yaml`](../schemas/config-keys.yaml)；门禁 `protocol-config-scan` 按它核对每个组件的 `configSchema`。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P2.1 | MUST | 配置**只**来自平台：单跑时来自进程环境；外壳里来自 `BRICKKIT_SERVED_MEMBERS_CONFIG` 中本成员自己的那一项（[P19](19-shells.zh.md)）。键就是环境变量名，与 brickKit 环境变量契约的定义完全一致 | — |
| P2.2 | MUST，部分 INTERNAL | 组件只读它 `configSchema` 里声明过的键，加上平台保留名（`COMPONENT_ID`、`COMPONENT_VERSION`、`PORT`、`<DEP>_ENDPOINT`、`<DEP>_<PORT>_ENDPOINT`）。官方 SDK 启动时读镜像里的 `component.yaml`，读没声明的键当作编程错误拒绝（退出 78）。组件代码从不自己读进程环境（INTERNAL） | CP-CORE-02 |
| P2.3 | MUST | 值按目录给每个键规定的格式严格定类型：`int`、`bool`（`true` / `false`）、`duration`（Go 语法）、`url`、`json`（一个对象）、`durations`（逗号分隔的多个时长）、`enum`、`string`。值有、但解析不了，就是配置错误（[P1.2](01-process-and-lifecycle.zh.md)，退出 78）；永不回退到默认值。有默认值的键给空串，表示用默认值。所有错误一起报告，每个一行日志 | CP-CORE-02 |
| P2.4 | MUST | 配置键不使用保留名，也不以 `_ENDPOINT` 结尾（brickKit 的规则：平台的值会静默胜出） | —（门禁） |
| P2.5 | MUST | 可选依赖没装时，它的 `*_ENDPOINT` 变量**不存在**（不是空的）。组件按它契约所写的方式降级，不崩溃 | — |
| P2.6 | MUST | 读依赖地址时，从注入的值里去掉 `http://` scheme 和末尾的 `/`。gRPC 一律用带端口名的变量 `<DEP>_GRPC_ENDPOINT`；拨 `<DEP>_ENDPOINT` 会连到 HTTP 端口。槽位族没有这类变量：它经共享的 `*_URL` 键访问（P2.10） | — |
| P2.7 | MUST | 声明为 `secret: true` 的键，在项目配置里只经 `${VAR}` 或 `file://` 注入。它的值永不出现在日志行、错误体、`/_be/info` 或指标标签里 | CP-OBS-04 |
| P2.8 | MUST | 组件在它的 `configSchema` 里声明它所用 profile 要求的每个协议键，带目录给出的 `type`、`secret` 标志和默认值。`AUTHZ_BUNDLE_URL` 不是协议键，不声明 | —（门禁 `protocol-config-scan`） |
| P2.9 | MUST | `secret: true` 的值如果文本是 `@file:<absolute path>`，就在用到时从该文件读取，文件修改时间变了就重读。这是运行期的文件引用，与 brickKit 的 `file://` 不同，后者在生成部署文件时就内联进去了 | — |
| P2.10 | MUST | 槽位族地址。槽位族已安装的成员只经族的共享键访问（权限族是 `AUTHZ_URL`，身份族是 `IAM_URL`），从不经依赖边，所以它没有任何 `*_ENDPOINT` 变量。取值是 `http://<成员服务名>:<成员 HTTP 端口>`，端口必须写明、不带路径（末尾的 `/` 去掉）；REST 路径直接拼在后面（`{AUTHZ_URL}/authz/v2/bundle`）。族的 gRPC 目标是推出来的，从不配置：URL 的主机，加 URL 的端口 **+ 1000**（`http://infra-authz-3-0-0:8223` → `infra-authz-3-0-0:9223`），所以族的每个成员都把自己的 `grpc` 额外端口登记为主端口 + 1000（由族的一致性套件检查）。没写端口、带路径、或端口 + 1000 超过 65535 的值是配置错误（退出 78） | —（向量 `config`） |
| P2.11 | MUST | 族键：少数共享键只由某个槽位族的成员读取，其他组件一律不声明；目录用 `applies_when` 标记它们，而不是 profile。1.0 只有一个：`BOOTSTRAP_ADMIN_LOGIN`，第一位管理员在 IdP 的登录名或邮箱。身份成员在这个人第一次登录时把它绑定到一个平台 `sub`，只绑一次，并在用户事件里写明（`bootstrap_admin: true`）；权限成员收到这条事件时授予它的初始管理员角色（contract-infra-iam `TOKENS.md`、contract-infra-authz `README.md`）。平台 `sub` 在第一次登录之前并不存在，所以没法事先配置 | —（门禁 `protocol-config-scan`） |

## 协议配置键

`Profile` 列说明哪些组件声明该键。默认值按目录里写的原样注入。`PG_POOL_MAX` 在外壳自己的配置里默认值不同（40）。

| 键 | Profile | 必填 | 默认 | 格式 | 含义 |
|---|---|---|---|---|---|
| `PG_HOST` | db | 是 | — | string | 共享的数据库主机 |
| `PG_PORT` | db | 否 | `5432` | int | 共享的数据库端口 |
| `PG_DATABASE` | db | 是 | — | string | 共享的数据库名 |
| `PG_USER` | db | 是 | — | string | 运行期角色（只做 DML）：服务的登录角色，也是每个运行期事务用 `SET LOCAL ROLE` 切换到的角色（[P10.1](10-database.zh.md)） |
| `PG_PASSWORD` | db | 是 | — | string，secret | `PG_USER` 的口令，每建一个新连接都读一次 |
| `PG_OWNER_USER` | db | 是 | — | string | 属主角色：拥有表，跑迁移；运行中的服务从不使用它（[P10.12](10-database.zh.md)） |
| `PG_OWNER_PASSWORD` | db | 是 | — | string，secret | 属主角色的口令，只由迁移步骤使用 |
| `PG_SCHEMA` | db | 是 | **无** | string | 组件的 schema；从不由角色推出，代码里从不写默认值 |
| `PG_POOL_MAX` | db | 否 | `10` | int | 单跑时：池的上限；外壳里：本成员在共享池里的并发预算（[P10.5](10-database.zh.md)） |
| `PG_POOL_MIN_IDLE` | db | 否 | `2` | int | 保持打开的空闲连接数 |
| `PG_POOL_ACQUIRE_TIMEOUT` | db | 否 | `5s` | duration | 取连接的最长等待，不超过剩余截止时间 |
| `PG_CONN_MAX_LIFETIME` | db | 否 | `30m` | duration | 连接用满这么久后被替换 |
| `PG_CONN_MAX_IDLE_TIME` | db | 否 | `5m` | duration | 空闲连接空闲这么久后被关闭 |
| `PG_MIGRATION_HOST` | db | 否 | `PG_HOST` | string | 迁移连到这里；当 `PG_HOST` 是 transaction 模式的 pooler 时设置 |
| `PG_MIGRATION_PORT` | db | 否 | `PG_PORT` | int | 同上 |
| `EVENT_BUS_URL` | events-pub, events-sub | 二选一 | 回退到 `NATS_URL` | url | scheme 选总线适配器：`nats://`、`postgres://…?schema=be_bus`；`kafka://` 预留（[P12.12](12-events.zh.md)） |
| `NATS_URL` | events-pub, events-sub | 二选一 | — | url | 共享的 NATS 地址 |
| `EVENTS_MAX_DELIVER` | events-sub | 否 | `8` | int | 消息进死信之前的投递次数，由运行时按 broker 的投递计数来数（[P12.7](12-events.zh.md)）；覆盖订阅自己的值 |
| `EVENTS_BACKOFF` | events-sub | 否 | `1s,10s,1m,5m,15m,30m,1h` | durations | 运行时的重投延迟，用带这个延迟的否定确认实现；broker 自己不设退避（[P12.5](12-events.zh.md)）；覆盖订阅自己的值 |
| `AUTHZ_URL` | auth | 是 | — | url | 已安装的授权 provider 成员的基础 URL，用该成员自己的服务名；gRPC 目标按 P2.10 推出 |
| `IAM_URL` | —（调用 `infra.iam.v1.IamProvider` 的组件；身份成员） | 否 | — | url | 已安装的身份成员的基础 URL，用该成员自己的服务名；gRPC 目标按 P2.10 推出。`IAM_JWKS_URL` 就是 `{IAM_URL}/.well-known/jwks.json` |
| `IAM_JWKS_URL` | auth | 是 | — | url | 身份 provider 的 JWKS |
| `IAM_ISSUER` | auth | 是 | — | string | 期望的 `iss`：这个部署的平台签发方的稳定名字，推荐 `urn:be:<TENANT_ID>:iam`；不是地址，换身份成员时不变 |
| `TENANT_ID` | auth | 是 | — | string | 期望的 `aud`（一个部署就是一个租户） |
| `BOOTSTRAP_ADMIN_LOGIN` | —（只有权限成员和身份成员，P2.11） | 否 | — | string | 第一位管理员在 IdP 的登录名或邮箱 |
| `BUSINESS_TIMEZONE` | jobs | 否 | `Asia/Shanghai` | string（IANA 时区） | 部署的默认时区；cron 日程按它求值。法人自己的时区来自 mdm/org（[P11.9](11-migrations-and-data-shapes.zh.md)） |
| `DATA_LIFECYCLE` | lifecycle | 否 | `{"mode":"on"}`（适配器都是 `none`） | json 或 YAML 映射 | 生命周期引擎的模式和适配器（[P16](16-data-lifecycle.zh.md)，[schema](../schemas/data-lifecycle-config.schema.json)） |
| `JOBS_OVERRIDES` | jobs | 否 | 空 | json | 按任务覆盖 `interval`、`cron`、`enabled`（[P14](14-background-jobs.zh.md)，[schema](../schemas/jobs-overrides.schema.json)） |
| `S3_URL` | blob | 是 | — | url | 对象存储端点 |
| `S3_PUBLIC_URL` | blob | 否 | `S3_URL` | url | 浏览器使用的地址；预签名 URL 按它签名（[P17.2](17-object-storage.zh.md)） |
| `S3_REGION` | blob | 否 | `us-east-1` | string | 签名用的 region |
| `S3_FORCE_PATH_STYLE` | blob | 否 | `false` | bool | path-style 寻址 |
| `S3_BUCKET` | blob | 是 | — | string | 组件自己的 bucket |
| `S3_ACCESS_KEY_ID` | blob | 是 | — | string，secret | 组件自己的凭据 |
| `S3_SECRET_ACCESS_KEY` | blob | 是 | — | string，secret | 同上 |
| `OTEL_BASE_URL` | all | 否 | 空（不导出） | url | OTLP/HTTP 基础地址；运行时自己补 `/v1/traces`（导出指标时还补 `/v1/metrics`） |
| `DEFAULT_LOCALE` | all | 否 | `zh-CN` | string（BCP 47） | 部署的默认语言：错误体 `title` 和 `detail` 所用的语言（[P4.1](04-errors.zh.md)）；每个部署一个值，共享 |
| `LOG_LEVEL` | all | 否 | `info` | enum `debug`、`info`、`warn`、`error` | 写日志的最低级别 |
| `HTTP_DEFAULT_TIMEOUT` | 有 HTTP 路由的全部组件 | 否 | `10s` | duration | 默认路由截止时间（[P3.4](03-http-surface.zh.md)） |
| `GRPC_MAX_CONNECTION_AGE` | grpc | 否 | `5m` | duration | 服务端连接的最长寿命（[P7.5](07-system-rpc.zh.md)） |
| `SHUTDOWN_GRACE` | all | 否 | `20s` | duration | `SIGTERM` 后允许在途工作的时间；保持小于平台的停机宽限 |

遵循协议模式、由组件自己定义的键：

| 模式 | 格式 | 含义 |
|---|---|---|
| `<SERIES>_NO_FORMAT` | string | 单据编号序列的格式（[P11.10](11-migrations-and-data-shapes.zh.md)），例如 `ORDER_NO_FORMAT` |

组件永不声明的保留名：`COMPONENT_ID`、`COMPONENT_VERSION`、`PORT`、所有 `*_ENDPOINT`、`BRICKKIT_SERVED_MEMBERS`、`BRICKKIT_SERVED_MEMBERS_CONFIG`。

## 说明

- 协议键同时是套件的可测试接口：套件通过运维调优用的同一批键把计时器调短（`EVENTS_BACKOFF`、`EVENTS_MAX_DELIVER`、`GRPC_MAX_CONNECTION_AGE`、`JOBS_OVERRIDES`）；没有"测试模式"开关。
- `DATA_LIFECYCLE` 有意承载一个结构化的值：拆平的话会是几十个键，而且没法表达按表覆盖。1.0 里组件级的值整体替换共享值（brickKit 的 `$var:` 总是一个完整的值）；两者的合并没有定义。
- 法人日历不是配置：它们来自 mdm/org。
