[English](02-configuration.md) · [中文](02-configuration.zh.md)

# P2 配置

组件的配置从哪里来、值怎么定类型和解析，以及本协议定义的键。机器可读的目录是 [`schemas/config-keys.yaml`](../schemas/config-keys.yaml)；门禁 `protocol-config-scan` 按它核对每个组件的 `configSchema`。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P2.1 | MUST | 配置**只**来自平台：单跑时来自进程环境；外壳里来自 `BRICKKIT_SERVED_MEMBERS_CONFIG` 中本成员自己的那一项（[P19](19-shells.zh.md)）。键就是环境变量名，与 brickKit 环境变量契约的定义完全一致 | — |
| P2.2 | MUST，部分 INTERNAL | 组件只读它 `configSchema` 里声明过的键，加上平台保留名（`COMPONENT_ID`、`COMPONENT_VERSION`、`PORT`、`<DEP>_ENDPOINT`、`<DEP>_<PORT>_ENDPOINT`）。官方 SDK 启动时读镜像里的 `component.yaml`，读没声明的键当作编程错误拒绝（退出 78）。组件代码从不自己读进程环境（INTERNAL） | CP-CORE-02 |
| P2.3 | MUST | 值按目录给每个键规定的格式严格定类型：`int`、`bool`（只能是 `true`、`false`、`1` 或 `0`，区分大小写）、`duration`（Go 语法）、`url`、`json`（一个对象）、`durations`（逗号分隔的多个时长）、`enum`、`string`。值有、但解析不了，就是配置错误（[P1.2](01-process-and-lifecycle.zh.md)，退出 78）；永不回退到默认值。空值一律算**没设**，各种格式都一样，`string` 也不例外：有默认值就用默认值，必填键没有值就是缺失（这段文字说不清的地方以向量 `config` 为准）。目录里标了 `one_of` 的键（`EVENT_BUS_URL`、`NATS_URL`）同组至少要设一个。所有错误一起报告，每个一行日志 | CP-CORE-02 |
| P2.4 | MUST | 配置键不使用保留名，也不以 `_ENDPOINT` 结尾（brickKit 的规则：平台的值会静默胜出） | —（门禁） |
| P2.5 | MUST | 可选依赖没装时，它的 `*_ENDPOINT` 变量**不存在**（不是空的）；槽位族成员这次不跑时，族的地址键同样不存在（P2.10）。组件按它契约所写的方式降级，不崩溃 | — |
| P2.6 | MUST | 读依赖地址时，从注入的值里去掉 `http://` scheme 和末尾的 `/`。gRPC 一律用带端口名的变量 `<DEP>_GRPC_ENDPOINT`；拨 `<DEP>_ENDPOINT` 会连到 HTTP 端口。槽位族没有这类变量：它经族的地址键 `*_URL` 和 `*_GRPC_URL` 访问（P2.10），读法相同 | — |
| P2.7 | MUST | 声明为 `secret: true` 的键**以文件交付**，从不作为环境变量的值：它声明 `mount: file`、名字是 `…_FILE`（P2.12），变量里是 brickKit 挂进来的文件路径 `/run/brickkit/secrets/<版本化服务名>/<键>`（`mode: local` / `debug` 时是宿主机路径；外壳里成员那一项带的是同一个路径，[P19](19-shells.zh.md)）。项目配置里它的值只写成 `${VAR}`、`file://`，或在 Kubernetes 上写 `existingSecret`。密钥的值永不出现在环境变量、日志行、错误体、`/_be/info` 或指标标签里 | CP-OBS-04、CP-CORE-14 |
| P2.8 | MUST | 组件在它的 `configSchema` 里声明它所用 profile 要求的每个协议键，带目录给出的 `type`、`secret`、`mount` 和默认值。`configSchema` 的这一段由 be-ops 按 profile 从目录生成，组件的这一段与生成结果不同时门禁失败；手写的只有组件自己的键，外加每个从其它清单看不出来的 profile 各一个**触发键**：`configSchema` 声明了 `PG_SCHEMA` 或 `PG_HOST` 就选中 `db`，声明了 `S3_BUCKET` 或 `S3_URL` 就选中 `blob`（README《Conformance》），其余的键由 be-ops 补齐。`AUTHZ_BUNDLE_URL` 和 `IAM_JWKS_URL` 不是协议键，不声明 | —（门禁 `protocol-config-scan`） |
| P2.9 | MUST | 密钥在用到时从它的文件读取，文件变了就重读：运行时比较文件的修改时间和大小，间隔最多 30 秒（可以用文件系统监听让它更快），从不为此重启，每次变化记一行点名该键的 INFO 日志。文本密钥去掉恰好一个末尾 LF 或 CRLF（向量 `config`，`secret_text`）；组件自己的二进制密钥逐字节交出。新值不重启就生效：数据库口令用于变更之后新建的连接（已有连接活到 `PG_CONN_MAX_LIFETIME`）；对象存储的一对凭据成对重读；签名密钥按它的 JWKS 重叠期轮换（contract-infra-iam `TOKENS.md`）。变更之后读不了的文件保留上一个有效值，记一行点名该键的 ERROR 日志，计数 `be_secret_reload_failures_total{key}`；启动时必填密钥读不了或为空是配置错误（退出 78）。brickKit 的 `file://` 与此无关：它在生成时填入文件内容 | CP-DB-06 |
| P2.10 | MUST | 槽位族地址。槽位族已安装的成员只经族的地址键访问，从不经依赖边，所以它没有任何 `*_ENDPOINT` 变量：权限族是 `AUTHZ_URL` 和 `AUTHZ_GRPC_URL`，身份族是 `IAM_URL` 和 `IAM_GRPC_URL`。项目在 `config/vars.yaml` 里把每个键写一次，写成指向该成员的 brickKit `$endpoint:` 引用（`AUTHZ_URL: $endpoint:infra/authz`、`AUTHZ_GRPC_URL: $endpoint:infra/authz:grpc`），组件用 `$var:` 取用；换成员时每个键改一行，值跟着版本、外壳和本机运行走，与 `*_ENDPOINT` 完全一样。取值是 `http://<主机>:<端口>`，端口写明，不带路径（末尾的 `/` 去掉）：REST 路径拼在 `*_URL` 的值后面（`{AUTHZ_URL}/authz/v2/bundle`），`*_GRPC_URL` 的值去掉 `http://` 就是 gRPC 拨号目标。任何值都不从别的值推出来：没有端口算术。成员这次不跑时 brickKit 不给这个键；可选的键于是降级，必填的键让启动停下。没写端口、带路径或用别的 scheme 的值是配置错误（退出 78） | —（向量 `config`） |
| P2.11 | MUST | 族键：少数共享键只由某个槽位族的成员读取，其他组件一律不声明；目录用 `applies_when` 标记它们，而不是 profile。1.0 只有一个：`BOOTSTRAP_ADMIN_LOGIN`，第一位管理员在 IdP 的登录名或邮箱。身份成员在这个人第一次登录时把它绑定到一个平台 `sub`，只绑一次，并在用户事件里写明（`bootstrap_admin: true`）；权限成员收到这条事件时授予它的初始管理员角色（contract-infra-iam `TOKENS.md`、contract-infra-authz `README.md`）。平台 `sub` 在第一次登录之前并不存在，所以没法事先配置 | —（门禁 `protocol-config-scan`） |
| P2.12 | MUST | 密钥的声明。`configSchema` 的一项是 `secret: true`，当且仅当它声明了 `mount: file`，也当且仅当它的名字以 `_FILE` 结尾；协议键和组件自己的键一样（`PG_PASSWORD_FILE`、`S3_SECRET_ACCESS_KEY_FILE`、`APP_TOKEN_SIGNING_KEY_FILE`）。别的键都不以 `_FILE` 结尾。brickKit 自己的规则同样成立：`mount: file` 只能和 `secret: true` 一起写，只能用于 `string` | CP-CORE-14（门禁 `protocol-config-scan`，向量 `config`） |

## 协议配置键

`Profile` 列说明哪些组件声明该键。默认值按目录里写的原样注入。`PG_POOL_MAX` 在外壳自己的配置里默认值不同（40）。目录的 `shell` 字段说明外壳用谁的值：`process` 键整个进程只有一个值，即外壳自己的，每个成员的值都必须与它相同（[P19.3](19-shells.zh.md)）；其余的键都用成员自己的值。

| 键 | Profile | 必填 | 默认 | 格式 | 含义 |
|---|---|---|---|---|---|
| `PG_HOST` | db | 是 | — | string | 共享的数据库主机 |
| `PG_PORT` | db | 否 | `5432` | int | 共享的数据库端口 |
| `PG_DATABASE` | db | 是 | — | string | 共享的数据库名 |
| `PG_USER` | db | 是 | — | string | 运行期角色（只做 DML）：服务的登录角色，也是每个运行期事务用 `SET LOCAL ROLE` 切换到的角色（[P10.1](10-database.zh.md)） |
| `PG_PASSWORD_FILE` | db | 是 | — | 路径，密钥文件 | 存放 `PG_USER` 口令的文件；文件变了就重读，新值用于新建的连接（P2.9） |
| `PG_OWNER_USER` | db | 是 | — | string | 属主角色：拥有表，跑迁移；运行中的服务从不使用它（[P10.12](10-database.zh.md)） |
| `PG_OWNER_PASSWORD_FILE` | db | 是 | — | 路径，密钥文件 | 存放属主角色口令的文件，只由迁移步骤读取 |
| `PG_SCHEMA` | db | 是 | **无** | string | 组件的 schema；从不由角色推出，代码里从不写默认值 |
| `PG_POOL_MAX` | db | 否 | `10` | int | 单跑时：池的上限；外壳里：本成员在共享池里的并发预算（[P10.5](10-database.zh.md)） |
| `PG_POOL_ACQUIRE_TIMEOUT` | db | 否 | `5s` | duration | 取连接的最长等待，不超过剩余截止时间 |
| `PG_CONN_MAX_LIFETIME` | db | 否 | `30m` | duration | 连接用满这么久后被替换 |
| `PG_CONN_MAX_IDLE_TIME` | db | 否 | `5m` | duration | 空闲连接空闲这么久后被关闭 |
| `PG_MIGRATION_HOST` | db | 否 | `PG_HOST` | string | 迁移步骤连到这里，直连 PostgreSQL；当 `PG_HOST` 是 transaction 模式的 pooler 时设置（[P11.1](11-migrations-and-data-shapes.zh.md)） |
| `PG_MIGRATION_PORT` | db | 否 | `PG_PORT` | int | 迁移步骤的端口 |
| `EVENT_BUS_URL` | events-pub, events-sub | 两个至少设一个 | 回退到 `NATS_URL` | url | scheme 选总线适配器：`nats://`、`postgres://…?schema=be_bus`；`kafka://` 预留（[P12.12](12-events.zh.md)） |
| `NATS_URL` | events-pub, events-sub | 两个至少设一个 | — | url | 共享的 NATS 地址 |
| `EVENTS_MAX_DELIVER` | events-sub | 否 | 目录里不给：没设就用订阅自己的值，再没有就是 `8` | int | 消息进死信之前的投递次数，由运行时按 broker 的投递计数来数（[P12.7](12-events.zh.md)）；设了就覆盖订阅自己的值 |
| `EVENTS_BACKOFF` | events-sub | 否 | 目录里不给：没设就用订阅自己的值，再没有就是 `1s,10s,1m,5m,15m,30m,1h` | durations | 运行时的重投延迟，用带这个延迟的否定确认实现；broker 自己不设退避（[P12.5](12-events.zh.md)）；设了就覆盖订阅自己的值 |
| `AUTHZ_URL` | auth | 是 | — | url | 已安装的授权成员的 REST 基础地址；`config/vars.yaml` 里写 `$endpoint:<成员 ID>`（P2.10） |
| `AUTHZ_GRPC_URL` | —（调用 `infra.authz.v2.AuthzProvider` 的组件：可共享资源类型的属主、调用 `Check` 或 `ListObjects` 的组件、身份成员） | 是 | — | url | 它的 gRPC 地址，`$endpoint:<成员 ID>:grpc`；拨号目标是去掉 `http://` 的值 |
| `IAM_URL` | auth | 是 | — | url | 已安装的身份成员的 REST 基础地址，`$endpoint:<成员 ID>`；JWKS 在 `{IAM_URL}/.well-known/jwks.json`（[P5.4](05-identity.zh.md)） |
| `IAM_GRPC_URL` | —（调用 `infra.iam.v1.IamProvider` 的组件） | 否 | — | url | 它的 gRPC 地址，`$endpoint:<成员 ID>:grpc`；没有时按身份契约所写降级 |
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
| `S3_ACCESS_KEY_ID_FILE` | blob | 是 | — | 路径，密钥文件 | 存放组件自己访问密钥 ID 的文件；与私密密钥一起重读 |
| `S3_SECRET_ACCESS_KEY_FILE` | blob | 是 | — | 路径，密钥文件 | 存放组件自己私密访问密钥的文件 |
| `OTEL_BASE_URL` | all | 否 | 空（不导出） | url | OTLP/HTTP 基础地址；运行时自己补 `/v1/traces`（导出指标时还补 `/v1/metrics`） |
| `DEPLOY_ENV` | all | 否 | `dev` | string | 部署的环境名（`dev`、`test`、`staging`、`prod`……），作为资源属性 `deployment.environment.name` 导出（[P18.1](18-observability.zh.md)）；每个部署一个值，共享 |
| `DEFAULT_LOCALE` | all | 否 | `zh-CN` | string（BCP 47） | 部署的默认语言：错误体 `title` 和 `detail` 所用的语言（[P4.1](04-errors.zh.md)）；每个部署一个值，共享。只用目录里有的语言：主语言子标签是 `zh` 或 `en` 就用那种语言，其它值一律退回 `en`，启动时记一行 WARN（不算配置错误） |
| `LOG_LEVEL` | all | 否 | `info` | enum `debug`、`info`、`warn`、`error` | 写日志的最低级别 |
| `HTTP_DEFAULT_TIMEOUT` | 有 HTTP 路由的全部组件 | 否 | `10s` | duration | 默认路由截止时间（[P3.4](03-http-surface.zh.md)） |
| `GRPC_MAX_CONNECTION_AGE` | grpc | 否 | `5m` | duration | 服务端连接的最长寿命（[P7.5](07-system-rpc.zh.md)） |
| `SHUTDOWN_GRACE` | all | 否 | `25s` | duration | `SIGTERM` 后允许在途工作的时间；至少比 `deployment.stopGracePeriodSeconds` 小 5 秒（[P1.12](01-process-and-lifecycle.zh.md)） |

遵循协议模式、由组件自己定义的键：

| 模式 | 格式 | 含义 |
|---|---|---|
| `<SERIES>_NO_FORMAT` | string | 单据编号序列的格式（[P11.10](11-migrations-and-data-shapes.zh.md)），例如 `ORDER_NO_FORMAT` |

组件永不声明的保留名：`COMPONENT_ID`、`COMPONENT_VERSION`、`PORT`、所有 `*_ENDPOINT`、`BRICKKIT_SERVED_MEMBERS`、`BRICKKIT_SERVED_MEMBERS_CONFIG`。后缀 `_FILE` 归以文件交付的密钥（P2.12）。

已退役、永不声明的名字：`AUTHZ_BUNDLE_URL`（用 `AUTHZ_URL`）、`IAM_JWKS_URL`（`{IAM_URL}/.well-known/jwks.json`）、`PG_PASSWORD`、`PG_OWNER_PASSWORD`、`S3_ACCESS_KEY_ID`、`S3_SECRET_ACCESS_KEY`（各自换成对应的 `…_FILE` 键）；`PG_POOL_MIN_IDLE`（已删除：连接池保留多少空闲连接是各运行时自己的行为，写在各 SDK 的文档里，范围受 [P10.5](10-database.zh.md) 约束）。

## 说明

- 协议键同时是套件的可测试接口：套件通过运维调优用的同一批键把计时器调短（`EVENTS_BACKOFF`、`EVENTS_MAX_DELIVER`、`GRPC_MAX_CONNECTION_AGE`、`JOBS_OVERRIDES`）；没有"测试模式"开关。
- `DATA_LIFECYCLE` 有意承载一个结构化的值：拆平的话会是几十个键，而且没法表达按表覆盖。1.0 里组件级的值整体替换共享值（brickKit 的 `$var:` 总是一个完整的值）；两者的合并没有定义。
- 法人日历不是配置：它们来自 mdm/org。
- `EVENTS_MAX_DELIVER` 和 `EVENTS_BACKOFF` 故意不在目录里给默认值：平台注入的默认值永远算"设了"，会悄悄盖掉每个订阅自己的值。优先级是：键有值用键，其次订阅自己的值，最后是内置默认值。
- 空值算没设，是因为 brickKit 把 `${NAME:-}` 和没设的 `$var:` 都写成空串：把它们当值，缺了的 `PG_SCHEMA` 就会变成空的 schema 名，而不是配置错误。
- 密钥用文件，是因为环境变量在 `docker inspect` 和 Pod 的 spec 里看得见，会被崩溃转储和调试输出带出去，而且进程启动时就定死了；文件可以在进程运行时换掉。brickKit 不加 `_FILE` 后缀：后缀是本协议的命名规则。Docker 上它挂一个只读目录（不用 compose 的 `secrets:`，那是单文件挂载，换了文件容器里看不到），Kubernetes 上挂投射的 Secret 卷，`existingSecret` 也一样。Podman 和开着 SELinux 的宿主机没有验证过：那里的目录挂载可能需要重新打标签。
- 族地址是由 `$endpoint:` 填写的显式键，而不是一条端口规则，因为成员真实的端口来自它自己的 `component.yaml`：成员的 gRPC 端口放在哪里都行，也不再需要拿手写的服务名去和 `brickkit.yaml` 比对。
