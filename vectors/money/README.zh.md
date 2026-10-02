[English](README.md) · [中文](README.zh.md)

# 语义向量：money

十进制字符串、列容量、小数位、舍入、分摊、计税、金额与币种成对、换算（协议 P11.6）。对应 SDK API：`money` 包（Go 的 `money.Parse`、`d.Round(scale, mode)`、`money.Amount`、`money.Allocate`、`money.ScaleOf`；Python 的 `besdk.money`；TypeScript 的 `@brickkit/be-sdk-ts/money`）。

## 文件

| 文件 | 用例数 | 操作 |
|---|---|---|
| `columns.json` | 9 | `column` |
| `currencies.json` | 45 | `minor_units` |
| `parse.json` | 57 | `parse` |
| `format.json` | 19 | `format` |
| `round.json` | 46 | `round`、`round_cash`、`round_qty` |
| `allocate.json` | 20 | `allocate` |
| `tax.json` | 13 | `tax_line`、`tax_document` |
| `arithmetic.json` | 31 | `add`、`sub`、`convert`、`line_amount` |
| `iso4217.json` | — | 数据：每门 SDK 内置的小数位表（165 个代码，ISO 4217 List One） |

## 操作

输入输出的数值都是十进制字符串；`mode` 可省略，默认 `HALF_AWAY_FROM_ZERO`。

| 操作 | 输入 | 期望 |
|---|---|---|
| `column` | `kind`：amount、price、cost、quantity、rate、ratio、factor、currency | `sql`、`precision`、`scale`、`integer_digits` |
| `minor_units` | `currency` | `minor_units` |
| `parse` | `value`、`kind`（列类别，或 `decimal` 表示不查容量） | `value`：规范形式（无前导零、无小数尾零、无 `-0`） |
| `format` | `value`、`currency` | 恰好带该币种小数位的 `value`；从不舍入 |
| `round` | `value`、`currency` 或 `scale`、`mode` | 该精度下的 `value` |
| `round_cash` | `value`、`currency`、`increment`（`0.05`）、`mode` | 舍入到 `increment` 的整数倍，按币种小数位书写 |
| `round_qty` | `value`、`rounding`（单位的舍入步长，`0.001`、`1`）、`mode` | 按 `rounding` 的精度书写 |
| `allocate` | `total`、`currency`、`weights[]` | `parts[]`，之和恰等于 `total` |
| `tax_line` / `tax_document` | `lines[]`（不含税金额）、`rate`（比率）、`currency`、`mode` | `line_taxes[]`、`total` |
| `add` / `sub` | `a`、`b`：`{value, currency}` | `{value, currency}` |
| `convert` | `amount`：`{value, currency}`、`rate`、`to`、`mode` | 以 `to` 计的 `{value, currency}` |
| `line_amount` | `quantity`、`price`、`discount`（比率）、`currency`、`mode` | `{value, currency}` |

## 规则

- **语法**：整串匹配 `^-?[0-9]+(\.[0-9]+)?$`；其它一切（指数、`+`、空格、`NaN`、`Infinity`、分隔符、`1.`、`.5`、非 ASCII 数字、JSON 数字、`null`）都是 `DECIMAL_SYNTAX`。
- **容量**（列，foundations 06）：金额 `(19,4)`，单价、成本、数量 `(19,6)`，汇率 `(19,10)`，比率 `(9,6)`，换算系数 `(24,12)`。整数位超过 `precision − scale` 是 `DECIMAL_OVERFLOW`；有效小数位超过 `scale` 是 `DECIMAL_SCALE`（尾零不算）。
- **带币种的金额**最多带该币种的小数位（`12.345` CNY 是 `DECIMAL_SCALE`）；`format` 从不舍入。
- **舍入**是精确运算（不经浮点）：`HALF_AWAY_FROM_ZERO`（默认）或 `HALF_EVEN`，是否"恰好一半"按精确值判断。结果为零时不带符号。
- **分摊**：每份 = 总额 × 权重 ÷ 权重之和，精确计算；每份向下取整到最小单位；按余数从大到小每份补一个最小单位，直到凑满总额；余数相同先给前面的行。负总额按绝对值分摊再整体取负。权重是 ≥ 0 的十进制字符串，且不能全为零。
- **按行计税**：每行税额各自舍入，合计为它们之和。**按单计税**：合计只舍入一次，再按各行不含税金额分摊到行。税率是 [0, 1] 内的比率。
- **币种成对**：不同币种的 `add` / `sub` 是 `CURRENCY_MISMATCH`；结果超出金额列是 `DECIMAL_OVERFLOW`。
- **换算**：`round(value × rate)` 到目标币种的小数位；汇率为正、最多 10 位小数，币种相同时必须恰为 1。
- **行金额**：`round(quantity × price × (1 − discount))`，最后只舍入一次。
- **币种代码**：三个大写字母（否则 `CURRENCY_INVALID`），且在 `iso4217.json` 里（否则 `CURRENCY_UNKNOWN`）。小数位为 N.A. 的代码（XAU、XDR、XXX、XTS……）不在表里。

## 错误

下面每一类来自请求数据时，线上都是 `INVALID_ARGUMENT`，字段写进 `violations[]`。

| 错误类 | 何时 |
|---|---|
| `DECIMAL_SYNTAX` | 不是十进制字符串 |
| `DECIMAL_OVERFLOW` | 整数位超出该列 |
| `DECIMAL_SCALE` | 小数位超出该列或该币种 |
| `CURRENCY_INVALID`、`CURRENCY_UNKNOWN` | 币种代码格式错或不认识 |
| `CURRENCY_MISMATCH` | 跨币种运算 |
| `ALLOCATION_INVALID` | 没有权重、有负权重、权重全为零 |
| `RATE_INVALID`、`RATIO_INVALID` | 汇率 ≤ 0，或同币种却不为 1；比率不在 [0, 1] |
| `ROUNDING_INVALID` | 舍入步长 ≤ 0，或现金舍入步长比币种最小单位还细 |
| `MODE_UNKNOWN`、`KIND_UNKNOWN` | 不认识的舍入模式或列类别 |

## 本处补定的口径

协议定了列规格、默认模式和"最大余数法"。这些向量另外补定了以下几点，请评审：输入接受前导零（`007.50`）；尾零永远不计入精度；负总额按绝对值分摊；按单计税按各行不含税金额分摊；`round_qty` 以单位的舍入步长（十进制）为参数；同币种换算要求汇率为 1。

## 重新生成

`python3 gen/gen_money.py`；交叉验证 `go run gen/xcheck_money.go .`（见 [../README.zh.md](../README.zh.md)）。`gen/iso4217-list-one.xml` 是生成小数位表所用的官方清单；换成更新的发布版即可更新 `iso4217.json`。
