[English](00-reading-the-spec.md) · [中文](00-reading-the-spec.zh.md)

# 怎么读本规范

每一章都用到的术语、要求等级和标识。读任何一章之前先读一遍本文。

## 术语

| 术语 | 含义 |
|---|---|
| 组件（component） | BrickEnterprise 项目里的一个 BrickKit 组件：一个镜像、一份 `component.yaml`、一份 `assembly.yaml`，ID 为 `<domain>/<name>` |
| 成员（member） | 托管在外壳进程里的一个组件。除非某条规则另有说明，组件的每条规则都适用于每个成员；成员的行为与同一个组件单独运行时完全相同 |
| 外壳（shell） | 托管同一门语言若干成员的一个进程（[P19](19-shells.zh.md)） |
| 运行时（runtime） | 组件内部实现本协议的那部分代码：官方 SDK，或其它语言里组件自己的代码 |
| 主端口（main port） | `deployment.port` 的 HTTP 端口（单跑时），或成员的 `httpPort`（外壳里） |
| 系统面（system plane） | 组件之间的 gRPC（[P7](07-system-rpc.zh.md)）；系统面上的每个调用方都是系统主体 |
| 用户面（user plane） | 人经边缘访问的 REST（[P3](03-http-surface.zh.md)） |
| `besdk_*` 表 | 运行时在组件 schema 里自有的表（[ddl/](../ddl/)）；组件的 SQL 从不读写它们 |
| profile | 一组有名字的一致性用例，按组件的清单文件选择（README 的 *一致性测试* 一节） |
| 套件（suite） | `brickKit/be-acceptance` 的黑盒一致性套件 `conformance/component/` |
| 截止时间（deadline） | 当前这单位工作必须完成的时间点；工作往下传递时它只会缩短（[P9](09-deadlines-and-retries.zh.md)） |
| 平台（the platform） | brickKit：它注入配置和 `*_ENDPOINT` 变量、生成部署文件、启动容器 |

时长用 Go duration 语法（`200ms`、`5s`、`15m`、`1h`）；大小用二进制单位（1 MiB = 1,048,576 字节）；时间点用 UTC 的 RFC 3339；业务日期用 `YYYY-MM-DD`。

## 要求等级

关键词 MUST、MUST NOT、SHOULD、SHOULD NOT 和 MAY，当且仅当以大写出现时，按 RFC 2119 和 RFC 8174 的描述理解。

中文镜像里，表格的等级列保留英文原词（MUST、SHOULD、MAY、INTERNAL）。正文里这些关键词译为：必须 = MUST，不得 = MUST NOT，应当 = SHOULD，不应当 = SHOULD NOT，可以 = MAY。

| 表格里的等级 | 含义 | 谁来检查 |
|---|---|---|
| **MUST** | 符合协议所必需；从外部可观察 | 套件；失败则整次运行失败 |
| **SHOULD** | 推荐；组件可以有理由地偏离 | 套件给出警告 |
| **MAY** | 可选的表面 | — |
| **INTERNAL** | 符合协议所必需（等同 MUST），但从进程外观察不到，例如"事务里不发网络调用" | 官方 SDK 自己的测试；其它语言由组件的 `AGENTS.md` 写明怎么守住，评审时核对 |

标为 **MUST，部分 INTERNAL** 的行，可观察的部分由套件测试，内部的部分由评审核对；该行会写明哪部分是哪种。

## 标识

- **要求 ID** 形如 `P<章>.<n>`，例如 `P7.5`。它们跨协议版本保持稳定：永不重新编号，永不复用，永不赋予新含义。在后续 major 里撤回的要求保留它那一行，标为已撤回。新要求取所在章的下一个空闲编号。
- **用例 ID** 形如 `CP-<GROUP>-<nn>`，例如 `CP-AUTH-03`，即测试某条要求的套件用例。分组：`CORE`、`OBS`、`ERR`、`AUTH`、`SCOPE`、`RPC`、`OUT`、`EVP`、`EVS`、`IDEM`、`DB`、`JOBS`、`LIFE`、`BLOB`、`SHELL`。用例 ID 同样只增不改。完整清单，以及每个用例所属的 profile 和它测的要求，见 [`schemas/conformance-cases.yaml`](../schemas/conformance-cases.yaml)。
- domain `be` 的 **reason**（`TOKEN_INVALID`、`DB_POOL_EXHAUSTED`……）列在 [`schemas/errors-be.yaml`](../schemas/errors-be.yaml)；正文用代码字体写它们。

## 协议不涵盖的内容

- 业务行为：组件自己的状态机、自己的 reason、自己的事件。
- 槽位族的族契约：授权 provider（`brickKit/contract-infra-authz`，major `authz/2`）和身份 provider（`brickKit/contract-infra-iam`，major `iam/1`）。本文只说组件怎么消费它们。
- brickKit 本身：`component.yaml`、注入的变量和部署文件生成是 brickKit 的契约；本文依赖它们，不往 `component.yaml` 里加任何东西。
- 任何一门语言的 API。官方 SDK 里的函数名见它们各自的文档。
