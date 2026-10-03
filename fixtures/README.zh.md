[English](README.md) · [中文](README.zh.md)

# 夹具

组件一致性套件所测夹具组件的契约与行为说明。这里没有可执行的东西：每门官方 SDK 在自己的 `examples/widget` 里实现 widget，peer 由套件的假对端应答。

## 组件

| 目录 | 组件 | 是什么 |
|---|---|---|
| [widget/](widget/README.zh.md) | `conformance/widget` 1.0.0 | 每门 SDK 都实现的夹具；碰到每个 profile；它的 `conformance/fixtures.yaml` 是真实组件照抄的金样本 |
| [peer/](peer/README.zh.md) | `conformance/peer` 1.0.0 | widget 的依赖；只有契约，由套件的假对端应答 |

## 实例

三门 SDK 各自构建一个 widget 实例，组件 ID 各不相同：`conformance/widget-go`、`conformance/widget-py`、`conformance/widget-ts`（外壳 profile 需要第二个实例时加后缀，`conformance/widget-ts2`）。实例按下面的规则从这些文件机械地派生：

| 要改的 | 不变的 |
|---|---|
| 组件 ID 字符串 `conformance/widget` 的每一处出现（`component.yaml` 的 `metadata.id`、`assembly.yaml` 的 `id` 与 `edge_routes`、`errors.yaml` 的 `domain`、OpenAPI 的 `servers` 地址、`fixtures.yaml` 里的路径） | 点分的名字：权限键 `conformance.widget.*`、资源类型与聚合类型 `conformance.widget.widget`、subject `conformance.widget.*.v1`、proto 包 `conformance.widget.v1` |

所以 REST 前缀（`/conformance/widget-go/…`）、错误的 domain、durable 名、`be-caller` 与 `ce-source` 因实例而异，而契约仍是同一族：就像槽位族的成员，每个实例都发布同样的 subject。`conformance/peer` 永不改名。

## 校验

写下这些文件时（2026-10-02）已核对：proto 带上 `be/v1/limits.proto` 与 `google/type/date.proto` 能编译，并通过 `buf lint`（STANDARD）；两个 OpenAPI 文件通过 `redocly lint`，零警告；`fixtures.yaml`、`errors.yaml`、`lifecycle.yaml`、`assembly.yaml` 和两个事件文件都通过 `schemas/` 的校验；样本通过各自事件 payload 的 schema；`migrations/0001_widget.sql` 能在 PostgreSQL 16 上执行，`fixtures.yaml` 里的 `observe.sql` 在其上能跑；`brickkit lint` 接受两个 `component.yaml`。2026-10-03 两个文件加上 `readinessCheck`、`deployment.stopGracePeriodSeconds`、端口 `protocol`、`events` 段和 `mount: file` 密钥之后，用 brickKit v1.3.1 重新核对：`brickkit lint` 没有报错（只有夹具目录的文档警告）。
