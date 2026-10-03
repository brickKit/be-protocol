[English](19-shells.md) · [中文](19-shells.zh.md)

# P19 外壳

外壳启动器和它的成员必须做到什么，才能让 N 个进程变成一个，而别的什么都不变。只有拥有官方 SDK 及该 SDK 启动器的语言才有外壳；成员的行为和同一个组件独立运行时完全一样。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P19.1 | MUST | 一个外壳只装**同一门语言、同一个 SDK 版本**的成员，成员编译或链接进外壳的镜像。启动时它读 `BRICKKIT_SERVED_MEMBERS_CONFIG`（缺失、为空或为 `null` 都是错误；`[]` 表示零个成员）。列出的成员没有编译进来，或者编译进来的版本和列出的不同（Go 的 build info、Python 的 `importlib.metadata`、成员包的 `package.json`），外壳就以退出码 **2** 退出，并点名是哪个成员 | CP-SHELL-01, CP-SHELL-02 |
| P19.2 | MUST | 每个成员用它自己那一项的 `config`、`httpPort` 和 `extraPorts`：它自己的 HTTP 服务器，和它自己的 gRPC 服务器及自己的拦截器链。成员之间互相调用走网络，和独立运行时完全一样；没有进程内传输 | CP-SHELL-08 |
| P19.3 | MUST | 整个进程恰好只有四样东西是共享的：OpenTelemetry 导出器和传播器（共享的导出器只由外壳在所有成员都停止之后关闭；停止一个成员只刷出这个成员自己的 span 队列）；token 验签器（JWKS）和 bundle；数据库物理池；总线连接。之所以能共享，是因为每个成员的 `AUTHZ_URL`、`IAM_URL`、`IAM_ISSUER`、`TENANT_ID`、`PG_HOST`、`PG_PORT`、`PG_DATABASE` 和 `EVENT_BUS_URL`（或 `NATS_URL`）都和外壳自己的相同；任何一项不同，外壳就以退出码 **78** 退出，并点名是哪个成员、哪个键。所有成员的配置错误一起报告 | CP-SHELL-03 |
| P19.4 | MUST | 其余的一切都按成员实例化：配置、logger、指标 registry、tracer provider 和 meter provider（`service.name` = 成员的 ID）、数据库 store（成员的身份和连接预算）、gRPC 连接和出站舱壁、durable 和订阅、作业、缓存、授权投影、生命周期引擎、advisory 锁的键 | CP-SHELL-04, CP-SHELL-05 |
| P19.5 | MUST | 外壳的登录角色对它的成员是 NOINHERIT 的：它不持有任何成员的权限，只通过 `SET LOCAL ROLE` 进入成员的角色，授权方式是 `GRANT <member role> TO <shell role> WITH INHERIT FALSE, SET TRUE`；因此外壳要求 PostgreSQL ≥ 16（独立运行的组件仍以 14 为下限）。所有后台路径在这个角色下都能工作。成员之间的隔离是运行时的职责，不是数据库的：外壳角色可以切换到每个成员的角色，所以只有运行时的 store 发出 `SET LOCAL ROLE`，并且总是切到成员自己的运行期角色 `PG_USER`（从不切到属主角色，外壳从不被授予属主角色），成员代码从不发出 `SET ROLE`（[P10.1](10-database.zh.md)） | CP-SHELL-07 |
| P19.6 | MUST | 外壳的 `/healthz` 只答外壳进程本身。一个成员初始化失败，整个外壳就启动失败（非 0）。成员失败的后台工作由与独立运行时相同的监督者重启；它从不永久停止，也从不让进程退出 | CP-SHELL-06 |
| P19.7 | MUST | 外壳在自己的端口上提供 `/healthz`，以及一个汇总了每个成员 registry、带 `component` 标签的 `/metrics`；每个成员自己的 `/metrics` 在它的端口上照常可用 | CP-SHELL-04 |
| P19.8 | MUST | 迁移在外壳启动之前，从每个成员自己的镜像里运行，从不在外壳里运行 | — |
| P19.9 | MUST | 外壳声明它自己的 `deployment.stopGracePeriodSeconds`（brickKit 原样用外壳的值，不从成员的值推出任何东西），至少是它编进来的任何成员的最大值；它自己的 `SHUTDOWN_GRACE` 也至少是成员里最大的那个。收到 `SIGTERM` 时它并发地停止各成员，所以停机耗时等于最慢的那个成员，并在这个宽限期内退出 | CP-SHELL-11 |
| P19.10 | MUST | 外壳声明 `readinessCheck: {type: http, path: /readyz}`（[P1.11](01-process-and-lifecycle.zh.md)）。它自己端口上的 `/readyz` 只在每个托管成员都就绪时答 `200`（P1.4，同样一旦满足就一直满足）；否则答 `503` `NOT_READY`，`metadata.waiting` 以逗号分隔列出还没就绪的成员的组件 ID。零个成员时答 `200`。每个成员自己的 `/readyz` 在它的端口上照常可用 | CP-SHELL-11 |

## 输入

| 变量 | 内容 |
|---|---|
| `BRICKKIT_SERVED_MEMBERS` | 所托管成员的服务名，逗号分隔，由 brickKit 设定 |
| `BRICKKIT_SERVED_MEMBERS_CONFIG` | 一个 JSON 数组，每个成员一项：`componentId`、`version`、`httpPort`、`extraPorts`（`[{"name": "grpc", "port": 9095}]`）和 `config`（成员的键，值已经求值完毕，包括它的 `*_ENDPOINT` 变量和 `$endpoint:` 的值；密钥键的值是它的文件路径 `/run/brickkit/secrets/<成员的服务名>/<键>`，brickKit 把文件挂进外壳的容器，所以外壳把 `config` 原样交给成员；`componentId` 和 `version` 代替 `COMPONENT_ID` 和 `COMPONENT_VERSION`） |

外壳自己的键（它的 `PG_USER` 登录角色、`PG_POOL_MAX` = 物理池大小，默认 40，以及 P19.3 的共享地址）来自它自己的配置，见 [P2](02-configuration.zh.md)。

## 启动顺序

1. 解析 `BRICKKIT_SERVED_MEMBERS_CONFIG` 和外壳自己的配置（P19.1）。
2. 对每个成员：已编译进来且版本是列出的那个（否则退出码 2）；共享的键和外壳的相同（否则退出码 78）；它的配置有效（所有错误一起报，退出码 78）。
3. 创建进程级共享的四样东西（P19.3）；池的大小为 `min(Σ members' PG_POOL_MAX, shell PG_POOL_MAX)`。
4. 对每个成员：它自己的运行时（P19.4）、它的初始化（失败就结束外壳）、它端口上的服务器、它受监督的后台工作。
5. 在外壳的端口上提供 `/healthz`、`/readyz`（P19.10）和汇总的 `/metrics`。
6. 收到 `SIGTERM` 时：停止接收，并发地停止各成员（[P1.6](01-process-and-lifecycle.zh.md)、P19.9），关闭共享资源，以 0 退出。

## 说明

- 每个成员独立运行，必须和合并运行时行为一样；项目用 `brickkit up --ignore-shells` 来检查这一点。
- 成员的端口由外壳打开，所以部署条目可以 `expose` 一个成员（brickKit ≥ v1.2.0）：Docker / Podman 上外壳的容器发布该成员的主端口；Kubernetes 上成员自己的 Ingress 指向成员自己的 Service，它选中的是外壳的 Pod。成员条目上的 `replicas`、`resources` 和 `labels` 不生效：外壳只是一个进程。
- 外壳重启会一次让所有成员下线；durable 消费者保留它们的位置，reconciler 接着推进进行中的流程，重试预算吸收这段空档。
