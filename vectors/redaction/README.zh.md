[English](README.md) · [中文](README.zh.md)

# 语义向量：redaction

哪些日志字段名带个人信息，以及 SDK 的日志 handler 写什么来代替（协议 P18.2；foundations 23）。对应 SDK API：组件没有可调的 API：每门 SDK 都在日志 handler 里、写出一行之前自动做，业务代码从不调用。

## 文件

| 文件 | 用例数 | 操作 |
|---|---|---|
| `redact.json` | 29 | `redact`、`protected_key` |

## 操作

| 操作 | 输入 | 期望 |
|---|---|---|
| `redact` | `record`：一条日志记录的 JSON 对象（信封字段加本次调用的字段） | 写出时的 `record` |
| `protected_key` | `key` | `protected`：`true` 或 `false` |

## 规则

- **受保护的名字**：`phone`、`mobile`、`id_card`、`password`、`bank_card`、`email`、`token`、`secret`、`authorization`、`cookie`、`set_cookie`、`api_key`（P18.2；`Set-Cookie`、`X-Api-Key`、`apiKey` 经键单词规则命中）。
- **键的词**：拆开 camelCase（`contactPhone` → `contact`、`phone`；`IDCard` → `id`、`card`），`-` 和 `.` 当 `_` 处理，转小写，按 `_` 切分。
- **匹配**：受保护名字的词在键的词里连续出现；最后一个词可以带复数 `s`。所以 `phone_number`、`access_token`、`user.email`、`old_bank_card_tail`、`emails` 匹配；`telephone`、`tokenizer`、`card`、`id` 不匹配。
- **替换**：匹配字段的值，不论类型（字符串、数字、布尔、null、对象、数组），都变成字符串 `[REDACTED]`，不再往里走。
- **递归**：不匹配的对象或数组继续往里走，里面每个键都按同样规则处理。
- **信封字段**（`time`、`level`、`msg`、`component_id`、`component_version`、`trace_id`、`span_id`、`request_id`）永远不动。
- **不扫描值**：`msg` 或 `note` 里的手机号原样保留。代码不得把个人信息写进自由文本。

## 错误

无：脱敏永不失败。

## 本处补定的口径

请评审：按整词匹配并允许复数 `s`（P18.2 只列了名字，没定匹配规则；精确匹配会漏掉最常见的 `phone_number`、`access_token`）；接受对 `token_type`、`phone_verified` 这类无害键的过度脱敏。这些语义是规范性的（P18.2）。这里没有覆盖：2 KiB 行截断（P18.2 写明了：行仍是合法 JSON，字符串值从最长的开始截短并以 `…[TRUNCATED]` 结尾，加上 `truncated: true`），它取决于各语言的 JSON 编码器，所以没有逐字节的向量；`error` 字段的文本是一个值，不被扫描。

## 重新生成

`python3 gen/gen_redaction.py`；交叉验证 `node gen/xcheck_redaction.mjs .`。
