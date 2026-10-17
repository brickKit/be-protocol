# 02 配置与密钥

依据：装配项目协议 19 的“配置”“密钥”；组件实现约定的“运行时是唯一入口”“合并安全”。值从哪里来（共享变量、组件配置、部署文件的覆盖）由 BrickKit 与协议 19 决定；本章规定组件怎样读、怎样拒绝。

## 读取

| 编号 | 层级 | 规则 | 检验 |
| --- | --- | --- | --- |
| P2.1 | 必须 | 组件只读取自己在组件清单 `configSchema` 中声明的键，以及下表的平台键；键名是大写下划线，与声明完全相同 | CK-CF-01 |
| P2.2 | 内部 | 模块代码从不读进程环境；单独运行时运行时从环境与挂载的文件取值，外壳中从该成员的配置（`BRICKKIT_SERVED_MEMBERS_CONFIG` 中它的 `config`）取值，再交给模块 | SDK 静态检查 |
| P2.3 | 必须 | 组件声明的键不以 `_ENDPOINT` 结尾，不与平台键同名 | 装配检查 |

平台键（由 BrickKit 注入，组件不声明）：`COMPONENT_ID`、`COMPONENT_VERSION`、`PORT`、所有 `*_ENDPOINT`、`BRICKKIT_SERVED_MEMBERS`、`BRICKKIT_SERVED_MEMBERS_CONFIG`。依赖地址只经运行时的地址访问器读取：可选依赖缺席时访问器返回“不存在”，不是空字符串，也不导致启动失败。

## 类型与解析

| 编号 | 层级 | 规则 | 检验 |
| --- | --- | --- | --- |
| P2.4 | 必须 | 值按声明的类型严格解析：`string` 原样；`integer` 十进制，可带负号，不带 `+`、空白与前导零；`boolean` 只认 `true` 与 `false`（小写）；`duration` 写成整数加单位 `ms`、`s`、`m`、`h`（例如 `1500ms`、`3s`），不认小数与组合；`decimal` 按装配项目协议 14 的十进制字符串；`enum` 只认声明的取值 | 向量 `config-parse` |
| P2.5 | 必须 | 空字符串等于未设置。未设置的必填键与不合法的值都是错误；不合法的值**不回退**到缺省值；未设置的可选键取声明的缺省值 | 向量 `config-parse` |
| P2.6 | 必须 | 所有错误一次报出后以退出码 78 退出（[01](01-lifecycle-and-health.md) 的 P1.9）：每个错误一行，写键名、错误类别（`missing`、`invalid`、`unknown_enum`、`out_of_range`）与期望的形式；**从不**写出密钥的值，非密钥的值也只写长度不超过 64 的前缀 | CK-CF-03 |

## 密钥

| 编号 | 层级 | 规则 | 检验 |
| --- | --- | --- | --- |
| P2.7 | 必须 | 声明 `secret: true` 的键可以直接给值，也可以给文件：设置 `<KEY>_FILE` 为文件路径时读文件内容（去掉结尾的一个换行）。两者同时设置是配置错误 | CK-CF-04 |
| P2.8 | 必须 | 以文件给出的密钥按“重读间隔”（起始值 30 秒）重读；内容变化时新的连接与请求使用新值，已建立的连接自然结束（数据库密码的轮换按装配项目协议 19：两个运行角色交替） | CK-CF-05 |
| P2.9 | 必须 | 密钥的值不出现在日志、错误对象、事件、审计正文、任务载荷与自描述端点中 | CK-CF-06 |

## 外壳

| 编号 | 层级 | 规则 | 检验 |
| --- | --- | --- | --- |
| P2.10 | 必须 | 外壳中每个成员的配置按本章独立解析与校验；任何成员不合法时外壳不启动，一次报出全部成员的全部错误，每行带成员组件 ID | CK-SH-01 |
| P2.11 | 必须 | 下表“进程级”的键在同一外壳的全部成员中必须一致（同一个消息系统、同一组身份与授权地址）；不一致时外壳不启动并点名成员与键。“按目标”的键（数据库）可以不同：同一目标（`PG_HOST`、`PG_PORT`、`PG_DATABASE` 相同）的成员共用一个物理连接池，不同目标各一个；同一目标的成员其余“按目标”的键必须一致（[05](05-database.md) 的 P5.1、P5.3） | CK-SH-02 |

## 共享连接键

多个组件共用的连接键用统一的名字，不按组件改名（装配项目协议 19）。“范围”一列：**进程级**的键在外壳中必须一致；**按目标**的键决定连接池；**成员级**的键各成员不同。

| 键 | 类型 | 密钥 | 范围 | 含义 |
| --- | --- | --- | --- | --- |
| `PG_HOST`、`PG_PORT`、`PG_DATABASE` | string、integer、string | 否 | 按目标 | 运行时的数据库目标；经事务模式连接池代理时指向代理 |
| `PG_USER`、`PG_PASSWORD` | string、string | `PG_PASSWORD` 是 | 成员级 | 运行角色的登录凭据（单独运行时直接以它登录） |
| `PG_SCHEMA` | string | 否 | 成员级 | 组件的 schema（注册表中的名字） |
| `PG_MIGRATION_HOST`、`PG_MIGRATION_PORT` | string、integer | 否 | 成员级 | 迁移入口直连数据库的地址；未设置时用 `PG_HOST`、`PG_PORT`（迁移绕过连接池代理） |
| `PG_OWNER_USER`、`PG_OWNER_PASSWORD` | string、string | `PG_OWNER_PASSWORD` 是 | 成员级 | 属主角色；**只有** `migrate` 入口读取，`serve` 不解析也不使用（服务进程不使用属主角色；凭据在同一容器中可见是已接受的平台限制） |
| `PG_POOLER_PREPARED` | boolean | 否 | 按目标 | 目标是事务模式的连接池代理、并且代理**不**支持协议层的预编译语句时设为 `false`；缺省 `true`（直连或代理已开启） |
| `PG_STATEMENT_TIMEOUT`、`PG_LOCK_TIMEOUT`、`PG_IDLE_IN_TX_TIMEOUT` | duration | 否 | 成员级 | 每个事务设置的超时，缺省 `5s`、`2s`、`10s`（[05](05-database.md) 的 P5.6） |
| `PG_POOL_FOREGROUND`、`PG_POOL_BACKGROUND` | integer | 否 | 成员级 | 成员的连接预算：前台与后台各自最多同时持有的连接，缺省 `8`、`4`（P5.2） |
| `BUS_URL` | string | 否 | 进程级 | 消息运输；scheme 选择适配器：`nats://` 为 JetStream，`pgqueue://` 为 PostgreSQL 队列（[06](06-events.md) 的 P6.16）；产生或订阅事件的组件必填 |
| `IMPLEMENTATION_INSTANCE` | string（UUID） | 否 | 成员级 | 实现实例：安装时生成的随机身份，事件与读取响应用它声明来源（P6.9）；产生事件的组件必填 |
| `DEPLOYMENT_ID` | string（UUID） | 否 | 进程级 | 部署身份：用户凭据的受众 `be:deployment:<它>`、服务证书的信任域（[08](08-identity-authz-audit.md) 的 P8.2、P8.5）；有受保护路由或系统面的组件必填 |
| `IAM_ISSUER`、`IAM_JWKS_URL` | string、string | 否 | 进程级 | 身份成员的签发方与公钥地址（P8.1、P8.2）；有受保护路由的组件必填 |
| `AUTHZ_GRPC_URL` | string | 否 | 进程级 | 授权成员的系统面地址（`$endpoint:` 引用，P8.9）；有受保护路由的组件必填 |
| `SERVICE_TLS_CERT_FILE`、`SERVICE_TLS_KEY_FILE`、`SERVICE_TLS_CA_FILE` | string | 否 | 成员级 | 服务身份的证书、私钥与部署的信任根文件（P8.5），按文件重读；有受保护路由、系统面或系统调用的组件必填 |
| `OTEL_URL` | string | 否 | 进程级 | 遥测的 OTLP/HTTP 导出地址；未设置时不导出（基本观测档只写本地日志与指标）。不用 OpenTelemetry 惯用的 `OTEL_EXPORTER_OTLP_ENDPOINT`：以 `_ENDPOINT` 结尾的键属于平台（P2.3），组件拿不到它的值 |
| `LOG_LEVEL` | enum（`debug`、`info`、`warn`、`error`） | 否 | 成员级 | 缺省 `info` |

外壳自己的键（写在外壳的配置中，不在成员的配置中）：

| 键 | 类型 | 密钥 | 含义 |
| --- | --- | --- | --- |
| `PG_SHELL_USER`、`PG_SHELL_PASSWORD` | string、string | `PG_SHELL_PASSWORD` 是 | 外壳共享池的登录角色（P5.1）；外壳承载的成员中有组件拥有数据库时必填，缺少时外壳不启动 |

身份与授权的地址、对象存储的键随相应章节加入本表。
