[English](README.md) · [中文](README.zh.md)

# be-protocol

BrickEnterprise 的**组件协议**：一个组件不论用什么语言写，要成为 BrickEnterprise 项目里合格的一员，在线上、表和配置这几层必须做到的全部事情。本仓库放规范正文、机器可读的 schema、运行时自有表的参考 DDL、语义向量和夹具组件契约。这里不放任何实现。

**协议版本：1.0。发布：`v1.0.0-rc.1`**（候选版本；试点组件通过后冻结为 `v1.0.0`）。

## 谁来实现

| 实现 | 语言 | 状态 |
|---|---|---|
| `brickKit/be-sdk-go` | Go | 官方 SDK，自 v0.6.0 起实现协议 1.0 |
| `brickKit/be-sdk-python` | Python | 官方 SDK，自 v0.6.0 起实现协议 1.0 |
| `brickKit/be-sdk-ts` | TypeScript | 官方 SDK，自 v0.6.0 起实现协议 1.0 |
| 其它任何实现 | 任何语言 | 任何语言写的组件，只要通过它所用 profile 的一致性套件，就可以加入项目；它可以单独运行；只有当它的语言有了官方 SDK 和外壳启动器之后，它才能加入外壳（[P19](spec/19-shells.zh.md)） |

三个官方 SDK 是本文的参考实现。**任何 SDK 都不得有本文没有写明的行为**；要加行为，先加在这里（[版本规则](#版本规则)）。

## 怎么读

- 先读 [spec/00-reading-the-spec.zh.md](spec/00-reading-the-spec.zh.md)：术语、要求等级、要求 ID 和用例 ID。
- 再读与你手头工作对应的那一章。每个协议领域一个文件，`P1` 到 `P20`：

| 章 | 文件 | 内容 |
|---|---|---|
| P1 | [01-process-and-lifecycle](spec/01-process-and-lifecycle.zh.md) | 入口、启动顺序、`/healthz`、`/readyz`、停机、监督、退出码 |
| P2 | [02-configuration](spec/02-configuration.zh.md) | 配置从哪里来、类型、协议配置键 |
| P3 | [03-http-surface](spec/03-http-surface.zh.md) | 路径、请求 ID、trace、截止时间、服务端超时、请求体上限、分页 |
| P4 | [04-errors](spec/04-errors.zh.md) | problem+json、gRPC `ErrorInfo`、GraphQL、reason 目录、日志级别 |
| P5 | [05-identity](spec/05-identity.zh.md) | JWT 验证、JWKS、claim、stale token |
| P6 | [06-authorization](spec/06-authorization.zh.md) | bundle、判定链、档位、主体集合、规范谓词、资源契约、投影 |
| P7 | [07-system-rpc](spec/07-system-rpc.zh.md) | gRPC 元数据、拦截器、服务端和客户端参数、重试、舱壁、批量上限 |
| P8 | [08-outbound-http](spec/08-outbound-http.zh.md) | 调其它组件的用户面 HTTP、第三方 HTTP、事务内不发网络调用 |
| P9 | [09-deadlines-and-retries](spec/09-deadlines-and-retries.zh.md) | 逐跳的时间预算、重试分层（汇总） |
| P10 | [10-database](spec/10-database.zh.md) | 身份、每事务设置、隔离级别与重试、连接池、探测、advisory 锁、认领 |
| P11 | [11-migrations-and-data-shapes](spec/11-migrations-and-data-shapes.zh.md) | 迁移规则、平台迁移、主键、金额、日期、法人、编号 |
| P12 | [12-events](spec/12-events.zh.md) | CloudEvents 信封、outbox、流、持久消费者、游标、处理函数、死信、重放 |
| P13 | [13-idempotency](spec/13-idempotency.zh.md) | 调用方命名空间、绑定、重放、检查顺序、保留期 |
| P14 | [14-background-jobs](spec/14-background-jobs.zh.md) | `every`、`singleton`、`cron`、`queue`、reconciler、监督、指标 |
| P15 | [15-snapshots](spec/15-snapshots.zh.md) | 其它组件数据的本地副本 |
| P16 | [16-data-lifecycle](spec/16-data-lifecycle.zh.md) | `lifecycle.yaml`、引擎、`RANGE_COLD`、`_lifecycle/*`、封存单元 |
| P17 | [17-object-storage](spec/17-object-storage.zh.md) | S3、每个组件一个 bucket、预签名 URL |
| P18 | [18-observability](spec/18-observability.zh.md) | trace、日志行、指标名 |
| P19 | [19-shells](spec/19-shells.zh.md) | 外壳启动器和它的成员必须做到什么 |
| P20 | [20-self-description-and-versioning](spec/20-self-description-and-versioning.zh.md) | `/_be/info`、组件声明的协议版本 |

- 每一章都只写线上层面：请求头、状态码、JSON 字段、表结构、配置键、指标名和日志字段名。这里没有任何一门语言的 API。
- 英文为准；每个 `X.md` 都有中文镜像 `X.zh.md`，`##` 章节相同。

## 仓库结构

| 路径 | 内容 | 是否规范性 |
|---|---|---|
| `spec/` | 协议正文，P1–P20 | 是 |
| `schemas/` | 正文引用的 JSON Schema（2020-12）和 YAML 目录（[索引](#schema-清单)） | 是 |
| `ddl/` | `besdk_*` 表的参考 DDL，PostgreSQL ≥ 14 | 是：SDK 的平台迁移产出的列、类型、键和索引必须与它完全一致 |
| `proto/` | `be/v1/limits.proto`（`max_items` 字段选项）、`be/lifecycle/v1/lifecycle.proto` | 是 |
| `openapi/` | 每个组件都要挂出的 REST 片段：`_authz`、`_shares`、`_lifecycle`、运维端点 | 是 |
| `vectors/` | 语义向量：带输入和期望输出的 JSON 用例，每个 SDK 的单元测试都读它（金额、日历、编号、指纹、信封推导、错误、配置解析、脱敏）。授权判定向量以族契约 `brickKit/contract-infra-authz`（`vectors/decision/`）为准，不在这里 | 是 |
| `fixtures/widget/` | 夹具组件 `conformance/widget`：它的契约、行为，以及黄金文件 `conformance/fixtures.yaml` | 是 |
| `fixtures/peer/` | widget 只有契约的依赖 `conformance/peer`，由套件的假 peer 应答（gRPC 和 HTTP） | 是 |
| `fs.go`、`go.mod` | 唯一的代码：用 `//go:embed` 把上面这些文件以 `fs.FS` 导出给 Go 使用方 | — |
| `Makefile`、`scripts/`、`buf.yaml`、`redocly.yaml`、`third_party/` | 本仓库自己的检查：`make check` 依次跑 schema 与表格一致性校验（`scripts/validate.py`）、ID 交叉引用（`scripts/xref.py`）、在一次性的 PostgreSQL 14 和 16 上的 DDL 测试（`scripts/ddltest.sh`）、`buf lint` / `buf build`、Redocly lint、`go vet`、向量是否最新、`SHA256SUMS` 和向量的独立交叉验证，每一步都在容器里；`third_party/` 放 widget 引用的 `google/type/date.proto` | — |

### Schema 清单

| 文件 | 校验或列出什么 |
|---|---|
| [`config-keys.yaml`](schemas/config-keys.yaml) | 协议配置键目录：键名、configSchema 类型、值格式、默认值、是否密钥、profile（由 `config-keys.schema.json` 校验） |
| [`errors-be.yaml`](schemas/errors-be.yaml) | domain `be` 的保留 reason（由 `errors-yaml.schema.json` 校验） |
| [`errors-yaml.schema.json`](schemas/errors-yaml.schema.json) | 组件的 `contracts/errors.yaml` |
| [`problem.schema.json`](schemas/problem.schema.json) | REST 错误体（RFC 9457，带 AIP-193 的成员） |
| [`envelope.schema.json`](schemas/envelope.schema.json) | 事件消息的 CloudEvents 头 |
| [`events-contract.schema.json`](schemas/events-contract.schema.json) | 组件的 `contracts/events/*.events.json` |
| [`access-token.schema.json`](schemas/access-token.schema.json) | 组件要求并读取的 access token claim（P5） |
| [`lifecycle.schema.json`](schemas/lifecycle.schema.json) | `migrations/lifecycle.yaml` v1 |
| [`data-lifecycle-config.schema.json`](schemas/data-lifecycle-config.schema.json) | `DATA_LIFECYCLE` 键的值 |
| [`jobs-overrides.schema.json`](schemas/jobs-overrides.schema.json) | `JOBS_OVERRIDES` 键的值 |
| [`assembly-protocol.schema.json`](schemas/assembly-protocol.schema.json) | 本协议读取的 `assembly.yaml` 键：`protocol`、`language`、`conformance`、`resources`、`requires_capabilities` |
| [`info.schema.json`](schemas/info.schema.json) | `GET /_be/info` 的响应 |
| [`fixtures.schema.json`](schemas/fixtures.schema.json) | 组件的 `conformance/fixtures.yaml` |
| [`conformance-cases.yaml`](schemas/conformance-cases.yaml) | 一致性 profile、每个 profile 何时适用，以及每个用例 ID 和它测的要求 |
| [`compconf-report.schema.json`](schemas/compconf-report.schema.json) | 套件的机器可读报告 |

## 一致性测试

黑盒套件是 `brickKit/be-acceptance` 的 `conformance/component/`（在组装项目里是 `tools/be-acceptance/conformance/component/`；非正式名 *compconf*）。它针对一个**正在运行的容器**来跑，从不读源码，所以对每门语言的评判方式完全相同。profile 按组件的清单文件自动选择：

| Profile | 何时适用 |
|---|---|
| `core` | 总是 |
| `obs` | 总是 |
| `err` | 总是 |
| `auth` | 组件有任何一个不是 Public 的路由 |
| `scope` | `data_scopes` 不是 `none`，或声明了 `resources` |
| `grpc` | 有一个 extra port 名为 `grpc` |
| `outbound` | `dependencies.components` 非空 |
| `events-pub` | 组件的事件契约列出了它发布的 subject |
| `events-sub` | 组件订阅了任何 subject（在它的 fixtures 里列出） |
| `idempotency` | 任何一个写操作接受 `idempotency_key` 或 `Idempotency-Key` |
| `db` | `configSchema` 声明了 `PG_SCHEMA` |
| `jobs` | 组件有数据库（平台任务总是存在） |
| `lifecycle` | 组件有数据库 |
| `blob` | `configSchema` 声明了 `S3_BUCKET` |
| `shell` | `component.yaml` 有 `shell.members` |

MUST 用例失败，整次运行就失败；SHOULD 用例失败只是警告。只有可选用例可以跳过，每个都要写原因，放在 `assembly.yaml` 的 `conformance.skip` 下。用例清单见 [`schemas/conformance-cases.yaml`](schemas/conformance-cases.yaml)。

黑盒观察不到的规则标为 **INTERNAL**：官方 SDK 用自己的测试守住它们；其它语言的组件在自己的 `AGENTS.md` 里写明每一条怎么守住，评审时核对。

## 版本规则

- **协议版本** `MAJOR.MINOR`（这里是 `1.0`）是组件声明的版本（`assembly.yaml` 里的 `protocol: "1.0"`），也在 `/_be/info` 里报告。套件每个 minor 保留一套用例；组件总是按它声明的版本来测。
- **发布 tag** 是带 `v` 的 semver（`v1.0.0`），因为 Go module 会导入本仓库。
  - **patch**：措辞、澄清、增加向量；没有语义变化。
  - **minor**：只增加可选的表面：新的能力位、新的可选端点、字段、请求头、键或 reason。1.0 已定义内容的含义永不改变。
  - **major**：任何会让一个原本符合的组件变得不符合的改动，包括某个行为变成必须。
- **要求 ID 和用例 ID 是稳定的**：永不重新编号，永不复用。新要求取它所在章的下一个空闲编号。
- **改动的顺序**是固定的：(1) 改这里的正文和 schema；(2) 加向量；(3) 加套件用例，并看到它们对一个故意做坏的夹具失败；(4) 三个 SDK 各自实现，各自的夹具组件通过；(5) 打 tag。
- **谁钉谁**：`be-acceptance` 钉一个确切的协议版本；`be-sdk-go` 在测试里导入本 module；`be-sdk-python` 和 `be-sdk-ts` 从某个 tag 复制 `vectors/` 和 `schemas/`（`make sync-vectors`），并核对 `vectors/SHA256SUMS`。复制测试数据不算导入代码。
- **族契约单独版本化**（`brickKit/contract-infra-authz`、`brickKit/contract-infra-iam`）。本文只写它们的 major，例如 `contract: authz/2.x`。

见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

Apache License 2.0，见 [LICENSE](LICENSE)。
