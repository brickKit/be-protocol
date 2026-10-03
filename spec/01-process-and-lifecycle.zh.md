[English](01-process-and-lifecycle.md) · [中文](01-process-and-lifecycle.zh.md)

# P1 进程与生命周期

组件的进程怎么启动、怎么报告健康、怎么停机、怎么扛住自己的错误、怎么退出。适用于单跑，也适用于外壳里的每个成员；外壳特有的补充见 [P19](19-shells.zh.md)。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P1.1 | MUST | 镜像有两个入口。默认命令起服务。`component.yaml` 里 `migration.command` 的命令跑迁移，成功时退出 0。两者用同一个镜像、同一份配置。平台在每次启动前都会跑迁移命令，所以它必须幂等：连续跑两次，两次都退出 0，第二次什么都不改（[P11](11-migrations-and-data-shapes.zh.md)）。官方 SDK 用一个带子命令的二进制：`[<binary>, migrate, up]` 迁移，`[<binary>]` 起服务；另外还有 `migrate status`、`migrate down <n>`，以及提供时的 `job run <name>`（[P14.8](14-background-jobs.zh.md)）。入口不认识的参数立即以 **64** 退出，在读配置之前，所以拼错的迁移命令永远不会变成第二个服务进程 | CP-CORE-01 |
| P1.2 | MUST | 启动顺序固定：(1) 读取并校验配置（[P2](02-configuration.zh.md)）；(2) 开端口；(3) **在后台**连接 PostgreSQL、事件总线、授权 provider 和 JWKS。缺必填键、值解析不了、或组件 ID 与注入的 `COMPONENT_ID` 不同时，每个问题打一行点名该键的 JSON 日志，进程以退出码 **78**（EX_CONFIG）退出。环境里根本没有 `COMPONENT_ID`，说明进程不是平台启动的：立即以 **64** 退出，与不认识的参数相同。暂时不可达的依赖按退避重试（0.5 s 起步、翻倍、上限 15 s）；进程不退出 | CP-CORE-02, CP-CORE-03 |
| P1.3 | MUST | 主端口上的 `GET /healthz` 和 `HEAD /healthz`，只要进程活着且在服务，就答 `200`。处理函数不碰任何依赖：不碰 PostgreSQL，不碰总线，不碰授权 provider，不碰其它组件。停掉 PostgreSQL 不改变它的回答 | CP-CORE-04 |
| P1.4 | MUST | 主端口上的 `GET /readyz`，在以下几项全部满足后答 `200`：已加载第一份授权 bundle（仅当组件有受保护路由时）；数据库身份探测已通过（[P10.7](10-database.zh.md)）；schema 的迁移版本等于镜像的迁移版本。否则答 `503`，带错误体，reason 为 `NOT_READY`，`metadata.waiting` 以逗号分隔列出缺了什么（`bundle`、`db_identity`、`migrations`）。一项一旦满足就一直算满足：之后 PostgreSQL、总线、授权 provider 或别的组件出故障，永远不会让 `/readyz` 变回 `503`（bundle 按 fail-static 保留，[P6.1](06-authorization.zh.md)），所以一次下游抖动不会把所有副本一起摘掉。平台经 `readinessCheck`（P1.11）探它：Kubernetes 只在它答 `200` 之后才把流量导给 Pod，Docker / Podman 上依赖方也在那之后才启动 | CP-CORE-05 |
| P1.5 | MUST | 加载第一份 bundle 之前，每个非 Public 路由（Authenticated 路由也算）先验 token（缺失或无效答 `401` `TOKEN_INVALID`，[P5](05-identity.zh.md)），再答 `503`，reason 为 `AUTHZ_NOT_READY`，因为过期检查和代理检查都要用 bundle（[P6.2](06-authorization.zh.md)）。Public 路由照常服务 | CP-AUTH-10 |
| P1.6 | MUST | 收到 `SIGTERM`：停止接收新请求和新投递；让在途请求在 `SHUTDOWN_GRACE`（默认 25 s）内完成；然后停止后台工作：取消正在跑的任务、释放租约、对在途消息 ack 或 nak、把 outbox 泵当前这一批收尾；最后以 **0** 退出。`SHUTDOWN_GRACE` 加上停后台工作的时间落在平台的停机宽限期（P1.12）之内，平台永远不必强杀进程 | CP-CORE-06 |
| P1.7 | MUST | 可恢复的错误永不结束进程。每一项后台工作（任务、worker、reconciler、消费者、outbox 泵、投影拉取、bundle 轮询）都受监督：失败或 panic 被恢复、记日志、计数，然后按 1 s 到 5 min 的指数退避重启；一项停下永远不会让另一项停下。单跑和外壳里行为完全相同 | CP-JOBS-05, CP-SHELL-06 |
| P1.8 | MUST | 致命错误以**非 0** 码退出：配置非法（78）；在服务入口上，schema 的迁移版本比镜像的新（迁移入口则记一条 WARN 并退出 0，这样回滚到旧镜像时不会被它的迁移步骤挡住）；缺少必需的数据库能力（[P10.7](10-database.zh.md)）；外壳成员没编译进来，或编译进来的是另一个版本（2，[P19.1](19-shells.zh.md)）；组件的一次性初始化失败或超过 30 s。初始化失败后，进程永远不以 0 退出 | CP-SHELL-01, CP-SHELL-02 |
| P1.9 | MUST | 镜像里有 `/bin/sh` 和 `wget`：平台经 shell 执行健康检查。基于 `scratch` 和 distroless 的镜像不符合协议 | CP-CORE-07 |
| P1.10 | MUST | 组件的一次性初始化（模块的 start 钩子）只做准备工作然后返回；它从不启动循环。周期性工作声明为任务（[P14.1](14-background-jobs.zh.md)） | —（INTERNAL，见 P14.1） |
| P1.11 | MUST | `component.yaml` 声明两项检查，brickKit（≥ v1.3.1）把它们变成引擎的探针：`healthCheck: {type: http, path: /healthz}`（存活与启动）和 `readinessCheck: {type: http, path: /readyz}`（就绪）。启动超过平台默认 60 秒的组件设置 `healthCheck.startPeriodSeconds` | CP-CORE-12 |
| P1.12 | MUST | `component.yaml` 声明 `deployment.stopGracePeriodSeconds`，即从停机信号到强杀的时间：除非组件需要更久，就是 **30**，并且总是至少 `SHUTDOWN_GRACE` + 5 秒，让进程自己做完 P1.6 并退出。brickKit 把它写成 compose 的 `stop_grace_period` 和 Kubernetes 的 `terminationGracePeriodSeconds`；部署条目可以覆盖它，同样保持这个余量。外壳声明它自己的值（[P19.9](19-shells.zh.md)） | CP-CORE-06, CP-CORE-12 |
| P1.13 | MUST | 每个端口都监听所有网络接口，IPv4 和 IPv6 都要（`0.0.0.0` 和 `::`，或一个双栈的 `::` socket）：平台的健康检查在容器里调用 `127.0.0.1`，Kubernetes 探测 Pod IP，调用方可能把服务名解析成任何一种地址族。只监听 IPv4 或只监听 `localhost` 的进程不符合协议 | CP-CORE-13 |

## 退出码

| 码 | 何时 |
|---|---|
| 0 | 收到 `SIGTERM` 后干净停机；迁移运行成功或无事可做 |
| 2 | 外壳拒绝了它的成员列表（[P19.1](19-shells.zh.md)） |
| 64 | 用法错误：入口不认识的参数（P1.1）、`job run` 给了不存在的任务名（[P14.8](14-background-jobs.zh.md)），或环境里没有 `COMPONENT_ID`（P1.2） |
| 78 | 配置错误：键缺失或解析不了、组件 ID 不一致、外壳成员的共享键与外壳的不同 |
| 其它任何非 0 | 其它任何致命错误（[P1.8](#要求)） |

## 运维端点

全部在主端口上，永不经边缘路由，不做认证：

| 路径 | 回答 | 定义于 |
|---|---|---|
| `GET`、`HEAD /healthz` | 活着时 `200`；body 为空或 `ok` | P1.3 |
| `GET /readyz` | `200`，或 `503` 错误体 `NOT_READY` | P1.4、P1.11 |
| `GET /metrics` | Prometheus 文本格式 | [P18.3](18-observability.zh.md) |
| `GET /_be/info` | 自描述 JSON | [P20](20-self-description-and-versioning.zh.md) |

它们的形状见 [`openapi/ops.yaml`](../openapi/ops.yaml)。

## 说明

- `/healthz` 只为进程本身作答，因为不这样的话，一次下游抖动就会让每个上游重启，在外壳里则是每个成员同时重启。
- 退出码 78 让运维不读日志就能分清"去改配置"和"程序崩了"。
- 存活和就绪是两个问题，后果也不同：存活检查失败会重启容器，就绪检查失败只是不给流量。`/readyz` 回答的是"这个进程能不能开始服务了"，所以它要等第一份 bundle，也所以一旦就绪，它就永远不因进程之外的东西失败。
- 停机宽限期是组件自己的事实（它的在途工作要多久收尾），所以由组件声明；`SHUTDOWN_GRACE` 是运行时在其中自己的预算。
