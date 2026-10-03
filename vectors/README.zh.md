[English](README.md) · [中文](README.zh.md)

# 语义向量

组件协议里"纯计算"那部分的跨语言测试向量：给定这个输入，每一个实现都必须给出恰好这个输出，或者恰好这个错误。每门官方 SDK 都在单元测试里跑它们（Go 直接 import 本仓库；Python 和 TypeScript 用 `make sync-vectors` 拷贝 `vectors/` 并核对 `SHA256SUMS`）。第四门语言的组件 SHOULD 跑。它们不对容器跑：那是 `tools/be-acceptance/conformance/component/` 里组件一致性套件的事。

## 领域

| 领域 | 锁定什么 | 协议条款 | 文件数 | 用例数 |
|---|---|---|---|---|
| [money](money/README.zh.md) | 十进制字符串、列容量、ISO 4217 小数位、舍入模式、现金舍入、分摊、按行 / 按单计税、金额与币种成对、换算、行金额 | P11.6 | 8 + `iso4217.json` | 240 |
| [idempotency](idempotency/README.zh.md) | 请求指纹（RFC 8785 + SHA-256）、重放 / 不一致 / 进行中的判定、键的来源、caller 命名空间、过期 | P3.7、P13 | 3 | 101 |
| [envelope](envelope/README.zh.md) | UUIDv7、由 outbox 行得出的 CloudEvents 头、causation 与 hop、入站接收与死信、状态模式游标、重投、流 / durable / 死信的命名 | P11.5、P12 | 6 | 118 |
| [calendar](calendar/README.zh.md) | 瞬时在法人时区里的业务日期（夏令时、非整点时区、被跳过的日子）、一天与一段日期的瞬时边界、任意起始月的会计期间与会计年度 | P11.7、P11.9 | 3 | 93 |
| [numbering](numbering/README.zh.md) | 单据号格式、格式按什么期间重置、无缺号与允许缺号两种分配模型 | P11.10 | 3 | 46 |
| [errors](errors/README.zh.md) | gRPC 码 ↔ HTTP 状态码、平台 reason、还原依赖返回的 REST 错误、SQLSTATE 归类、日志级别、problem+json 错误体、`Retry-After`、reason 命名 | P4、P10.4 | 4 | 123 |
| [config](config/README.zh.md) | 配置值的类型化解析、默认值与"有没有"、时长、布尔、密钥文件、依赖地址变量、槽位族地址、键名与密钥声明、`config/*.yaml` 里的取值写法（含 `$endpoint:`） | P2 | 4 | 196 |
| [redaction](redaction/README.zh.md) | 哪些日志字段名算个人信息、怎么脱敏 | P18.2 | 1 | 29 |
| authz | bundle 求值、档位、维度、主体集合 | P6 | — | 在 `contract-infra-authz`（lane K1）；发版后拷到这里 |
| lifecycle、search | 生命周期 Planner、搜索规范化 | P16、data-platform §7.4 | — | 以后 |

合计：32 个用例文件，946 条用例。

## 用例文件格式

每个主题一个 JSON 文件 `vectors/<area>/<topic>.json`，格式见 [case-file.schema.json](case-file.schema.json)：

| 字段 | 含义 |
|---|---|
| `area`、`topic` | 目录名与文件名 |
| `protocol` | 文件锁定的是哪个协议版本的语义（`1.0`） |
| `generated_by` | 生成脚本；文件永远不手改 |
| `notes` | 可选，生成时的事实（tz 数据库版本、ISO 4217 发布日期） |
| `cases[].id` | `<area>.<topic>.<slug>`，永久稳定：不改名、不重编号、不复用 |
| `cases[].description` | 一句话说明这条用例 |
| `cases[].op` | 操作名；各领域 README 列出它的操作及输入输出形状 |
| `cases[].refs` | 这条用例对应的协议条款（`P11.6`）或 RFC 小节 |
| `cases[].input` | 操作的输入 |
| `cases[].expected` | 精确的输出，按深度相等比较 |
| `cases[].expected_error.reason` | 操作必须以这个错误失败，代替 `expected` |

`expected` 与 `expected_error` 恰好出现一个。

## SDK 怎么跑

1. 逐文件、逐用例，按 `op` 分派到它对应的 SDK 函数（各领域 README 给出操作与 SDK API 的对应）。
2. 有 `expected`：函数必须成功，结果按 README 给的形状呈现后与 `expected` 深度相等。
3. 有 `expected_error`：函数必须失败，SDK 的错误必须带这个 reason。`expected_error` 里的 reason 是**向量错误类**，每个领域列出它在线上变成什么错误；与平台 reason 同义的（`IDEMPOTENCY_MISMATCH`）用同一个名字。
4. 向量失败就是 SDK 的 bug，不是向量的，除非人另作决定（06-testing 的铁律）。向量本身错了，改生成器，单独一个提交并写明原因。

Go：`besdktest.Vectors(t, dir, run)` 遍历一个目录。Python、TypeScript：每个文件一个参数化测试。

## 向量暴露出来的实现要点

- **每个模式都要锚定整个字符串。** Python 的 `re.match(r"…$")` 会接受结尾的换行；`"12\n"` 在 Go 交叉验证抓到之前一直被当成合法十进制数。用 `re.fullmatch`、Go 的 `^…$`、JavaScript 不带 `m` 标志的 `^…$`。
- **JSON 里的数字是 IEEE 754 双精度。** 这些文件里所有整数都在 ±(2^53−1) 以内（I-JSON，RFC 7493 §2.2）。64 位的值（比如以纳秒计的时长）写成十进制字符串。
- **库的默认行为比协议宽**：Go 的 `strconv.ParseBool` 接受 `TRUE` 和 `t`，`strconv.ParseInt` 接受 `+5`，`net/url` 会把 scheme 转小写；Python 的 `decimal.Decimal` 接受 `1_000`、前后空格、`1e5`、`NaN` 和全角数字，Python 的 `json` 接受 `NaN`；JavaScript 的 `Intl` 把 `asia/shanghai` 和 `+08:00` 当成合法时区；npm 包 `canonicalize` 会把非有限数打印成 `null`。每一条向量里都有对应用例。

## 生成与交叉验证

每个期望值都由生成器 `vectors/<area>/gen/gen_<area>.py` 算出（Python ≥ 3.11，只用标准库，结果确定），再由一份不共享任何代码的独立实现重算一遍：

| 领域 | 第二份计算 |
|---|---|
| money | Go，`math/big.Rat`（`gen/xcheck_money.go`）；ISO 表另与一份手敲的清单核对 |
| idempotency | Node，npm 包 `canonicalize`（RFC 8785 作者的参考实现）加 `node:crypto` |
| envelope、numbering、redaction | Node，照协议正文另写一份 |
| calendar | Node，`Intl.DateTimeFormat` 用 ICU 的时区数据（生成器用 Python `zoneinfo` 读系统 tz 数据库） |
| errors | Go，按 foundations 15 重新敲一遍表 |
| config | Go，真实的 `time.ParseDuration`、`net/url`、`encoding/json`，上面叠加协议规则 |

```sh
cd vectors
make gen       # 重新生成
make xcheck    # 在一次性的 golang:1.22-alpine / node:22-alpine 容器里交叉验证
make sums      # 重写 SHA256SUMS
```

最近一次（2026-10-03）：946 条用例，0 处不一致；两边都是 tz 数据库 2026c；ISO 4217 List One 发布于 2026-09-17。首轮发现并已修正的不一致：1 处（上面结尾换行那条）。

## 版本

- 新增用例或文件，是 be-protocol 的 patch 版本。
- 改一个期望值就是改语义：按协议的 minor / major 规则走（本仓库 README 的"版本"一节）；只有旧行为本来就是 bug 时，用例才保留原 id。
- `SHA256SUMS` 列出全部向量文件；Python 和 TypeScript SDK 拷贝后核对它。
