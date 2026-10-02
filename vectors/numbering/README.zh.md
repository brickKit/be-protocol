[English](README.md) · [中文](README.zh.md)

# 语义向量：numbering

单据号格式（`<NAME>_NO_FORMAT`）、格式按什么期间重置，以及无缺号与允许缺号两种序列的分配模型（协议 P11.10；foundations 04）。对应 SDK API：Go 的 `Series` 与 `tx.NextNumber(series)`，Python、TypeScript 同名；表 `besdk_number_series`（附录 A）。

## 文件

| 文件 | 用例数 | 操作 |
|---|---|---|
| `format.json` | 28 | `format_number` |
| `period.json` | 7 | `period_key` |
| `series.json` | 11 | `series_sim` |

## 操作

| 操作 | 输入 | 期望 |
|---|---|---|
| `format_number` | `format`、`legal_entity_code`、`business_date`、`seq` | `number` |
| `period_key` | `format`、`business_date` | `period`：按公历重置的序列写进 `besdk_number_series.period` 的值 |
| `series_sim` | `mode`（`gapless` 或 `gapped`）、`block_size`（gapped 用）、`steps[]`：`{tx, op: alloc, scope, period[, process]}`、`{tx, op: commit}`、`{tx, op: rollback}`、`{op: crash, process}` | `committed[]`（每个到达提交的号码的 `tx`、`scope`、`period`、`number`）、`series_rows[]`（表里留下的 `scope`、`period`、`next_value`） |

## 规则

- **占位符**：`{le}`（法人代码，`[A-Za-z0-9_-]{1,32}`）、`{yyyy}`、`{yy}`、`{mm}`（取法人时区下的业务日期）、`{seq:N}`（补零到 N 位，N 为 1–18，写作 `5` 或 `05`）。别无其它：`{dd}`、`{seq}`、`{YYYY}`、多出来的花括号、字面文本里的空白或控制字符，都是 `FORMAT_INVALID`。字面文本可以是其它任何字符，含中文（`记-`）。
- **恰好一个 `{seq:N}`**：没有是 `FORMAT_NO_SEQUENCE`，两个是 `FORMAT_INVALID`。
- **序号比 N 位宽**时照写全，不截断。
- **格式按什么期间重置**由它最细的日期占位符决定：有 `{mm}` → 按月，期间 `YYYY-MM`；只有 `{yyyy}` / `{yy}` → 按年，期间 `YYYY`；都没有 → 不重置，期间为空。按月的格式还必须带年，否则一年后号码重复：`FORMAT_REPEATS`。法人是序列的 `scope`，所以号码里的 `{le}` 可有可无。
- **无缺号序列**（凭证）：分配时在业务事务里锁住序列行；因此每个（序列、scope、期间）的事务是串行的；回滚会撤销自增，提交的号码连续。凭证序列按会计期间的 `period_key`（`2026-P07`，见 calendar 向量）计。
- **允许缺号的序列**：每个进程在自己的短事务里预留 `block_size` 个号码并提交，然后从内存里发；回滚和崩溃留下缺号；号码唯一，在一个进程内递增，跨进程不保证。
- 无缺号的号码只在幂等认领成功之后才分配（P13.5），所以重放永远不会消耗号码。
- **唯一性**不是这些模拟要验证的性质：运行时在单据的事务里把每个格式化后的号码记进 `besdk_number_allocations`（主键 `(legal_entity_id, series, number)`，不分区），所以重复会让那个事务失败（P11.10）。

## 错误

| 错误类 | 何时 |
|---|---|
| `FORMAT_INVALID` | 不认识的占位符、宽度不对、字面文本里有花括号或空白、两个序号、空格式 |
| `FORMAT_NO_SEQUENCE` | 没有 `{seq:N}` |
| `FORMAT_REPEATS` | 按月重置却不带年 |
| `SEQ_INVALID` | 序号小于 1 |
| `LEGAL_ENTITY_CODE_INVALID` | `{le}` 的值含 `[A-Za-z0-9_-]` 以外的字符或长于 32 |

这些来自 `<NAME>_NO_FORMAT` 时都是配置错误：组件启动时以退出码 78 退出并点名该键。

## 本处补定的口径

请评审：宽度写作 `N` 或 `0N`（文档里的默认值 `{seq:05}` 用的是后一种）；序号超宽就变宽；期间键由格式里的占位符推出；不带年的按月格式拒收；`{le}` 用法人代码而不是 id；允许缺号序列的块大小是 SDK 参数，不是协议常量。

## 重新生成

`python3 gen/gen_numbering.py`；交叉验证 `node gen/xcheck_numbering.mjs .`。
