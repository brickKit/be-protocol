[English](README.md) · [中文](README.zh.md)

# 语义向量：calendar

由瞬时按法人时区得出业务日期、一天或一段日期的瞬时边界、按月的会计期间与会计年度（协议 P11.7、P11.9；foundations 05）。对应 SDK API：Go 的 `Calendar.BusinessDate` / `Today` / `FiscalPeriod` 与 `Date`，Python、TypeScript 同名。

## 文件

| 文件 | 用例数 | 操作 |
|---|---|---|
| `business_date.json` | 46 | `business_date` |
| `bounds.json` | 29 | `day_bounds`、`date_range`、`parse_date` |
| `fiscal.json` | 18 | `fiscal_period`、`fiscal_year` |

每个文件的 `notes.tzdata` 写明计算期望值时用的 tz 数据库版本（2026c）。

## 操作

| 操作 | 输入 | 期望 |
|---|---|---|
| `business_date` | `instant`（RFC 3339 UTC，带 `Z`）、`time_zone`（IANA 名） | `date`（`YYYY-MM-DD`） |
| `day_bounds` | `date`、`time_zone` | `start`、`end`：这一天的半开瞬时区间，以及 `hours`（23、24 或 25……） |
| `date_range` | `first`、`last`、`time_zone` | `start` = `first` 的起点，`end` = `last` 次日的起点 |
| `parse_date` | `value` | `date` |
| `fiscal_period` | `date`、`start_month`（1–12） | `fiscal_year`、`fiscal_year_label`、`period`（1–12）、`period_key`、`start_date`、`end_date`、`label` |
| `fiscal_year` | `fiscal_year`、`start_month` | `start_date`、`end_date`、`periods[]`（12 项） |

## 规则

- **业务日期** = 该瞬时在该时区里的民用日期。不问数据库；永远不拿 `DATE` 和 `timestamptz` 比。
- **一天的起点** = 民用日期为这一天的第一个瞬时。它不一定是当地零点：夏令时在零点开始时（圣保罗，2018-11-04），这一天从 01:00 开始。一天可能是 23 或 25 小时。某个时区跳过的日期（阿皮亚，2011-12-30）没有边界：`DATE_NONEXISTENT`。
- **输入的瞬时**是带 `Z` 的 RFC 3339 UTC（最多 6 位小数秒）；带偏移量、本地时间、只有日期，都是 `INSTANT_INVALID`。
- **时区**是 IANA 名，精确匹配、区分大小写，形如 `UTC` 或 `Area/Location`。偏移量（`+08:00`）、`UTC+8`、不认识的名字、大小写不对，都是 `TZ_UNKNOWN`。`Etc/GMT-8` 合法，表示 UTC+8（POSIX 符号相反）。链接名（`Asia/Calcutta`）有意不收：它存不存在取决于装的 tz 数据库（Debian/Ubuntu 没装 `tzdata-legacy` 时就没有），所以法人只存规范名，每门 SDK 自带 tz 数据（Go `time/tzdata`、Python `tzdata`、Node 完整 ICU）。
- **输入的业务日期**必须恰好是 `YYYY-MM-DD`；其它写法或不存在的日期都是 `DATE_INVALID`。
- **会计年度** = 它开始那一年的公历年份。起始月为 `s` 时，`m` 月的日期落在会计年度 `y`（`m ≥ s`）或 `y − 1`（否则）的第 `(m − s) mod 12 + 1` 期。`period_key` = `<会计年度>-P<NN>`（`2026-P07`）；`label` = 公历月份（`2026-10`），只用于显示；`fiscal_year_label` 在一月起始时是 `2026`，否则是 `2026/27`。

## 错误

| 错误类 | 何时 |
|---|---|
| `TZ_UNKNOWN` | 时区不是 tz 数据库认识的 IANA 名 |
| `INSTANT_INVALID`、`DATE_INVALID` | 输入格式错或不存在 |
| `DATE_NONEXISTENT` | 这个民用日期在该时区被跳过 |
| `RANGE_INVALID` | `last` 早于 `first` |
| `FISCAL_START_INVALID` | 起始月不在 1–12 |

## 本处补定的口径

请评审：会计年度以开始那一年命名；`period_key` 用 `-Pnn` 形式，永远不会被误读成公历月份；`fiscal_year_label` 用 `YYYY/YY`。边界精确到秒（没有哪个时区在小数秒上切换偏移）。

## 重新生成

`python3 gen/gen_calendar.py`（需要系统 tz 数据库，版本写进文件）；交叉验证 `node gen/xcheck_calendar.mjs .`（ICU）。两边必须是同一个 tz 版本；版本变了，一起重新生成、一起交叉验证。
