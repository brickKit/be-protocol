[English](README.md) · [中文](README.zh.md)

# 语义向量：idempotency

请求指纹、同一个键再次出现时怎么判定、键从哪里来、caller 命名空间（协议 P3.7、P13；foundations 11）。对应 SDK API：Go 的 `besdk.Idempotent` / `Command`，Python、TypeScript 同名；指纹函数是内部的，但要让 SDK 自己的测试能调到。

## 文件

| 文件 | 用例数 | 操作 |
|---|---|---|
| `fingerprint.json` | 76 | `fingerprint` |
| `decide.json` | 13 | `decide` |
| `keys.json` | 12 | `resolve_key`、`caller_namespace`、`expires_at` |

## 操作

| 操作 | 输入 | 期望 |
|---|---|---|
| `fingerprint` | `json_text`：指纹对象的原始 JSON 文本，由 SDK 自己的 JSON 解析器解析 | `canonical`：RFC 8785（JCS）规范文本；`sha256`：其 UTF-8 字节的 SHA-256 小写十六进制（即 `request_hash` 列） |
| `decide` | `rows`：该 caller 的 `besdk_idempotency` 行；`now`；`incoming`：`caller`（`{kind: user, sub}`、`{kind: system_call, be_caller}`、`{kind: background}`）、`key`、`command`、`target`、`request`（JSON 文本） | `caller`（命名空间）与 `outcome`：`EXECUTE`（认领并执行）、`REPLAY`（带存下的 `result`），或 `REJECT` 带 `code`、`http`、`reason` |
| `resolve_key` | `header`（`Idempotency-Key`）、`body`（`idempotency_key`），都可为 `null` | `key`（`null` 表示不走幂等） |
| `caller_namespace` | `caller` | `caller`：`user:<sub>`、`svc:<be-caller>` 或 `system` |
| `expires_at` | `created_at` | `expires_at` = created_at + 30 天（720 h） |

## 规则

- **JSON 输入按 I-JSON**（RFC 7493）：重复的成员名、`NaN`、`Infinity`、超出双精度范围的数、任何非 JSON 文本，都是 `JSON_INVALID`。
- **每个数字都是 IEEE 754 双精度**，按 ECMAScript 方式书写（RFC 8785 §3.2.2.3）：`1.0`、`1E0`、`100e-2` 都是 `1`；`-0` 是 `0`；`1e21` 及以上、`1e-6` 以下用指数形式；超过 2^53 的整数塌缩到最近的双精度值。Python 实现不得保留精确的大整数。
- **字符串不做规范化**：同一个词的 NFC 与 NFD 形式哈希不同。转义：`\"`、`\\`、`\b \t \n \f \r`，其它控制字符写 `\u00xx`（小写）；其余一切（包括 U+007F、U+2028、U+2029）原样输出 UTF-8。
- **成员按 UTF-16 码元排序**，不是按码点：U+1F600（`😀`）排在 U+FFFF 前面。
- **指纹对象里永远不含幂等键本身**；它装的是该命令声明参与指纹的业务字段。
- **判定顺序**：(caller, key) 没有行，或 `now ≥ expires_at` → `EXECUTE`；然后 `command`、`target`、`request_hash` 任一不同 → `INVALID_ARGUMENT` / 400 / `IDEMPOTENCY_MISMATCH`（先于状态判断，所以对进行中认领的不一致重试算不一致）；然后 `CLAIMED` → `ABORTED` / 409 / `IDEMPOTENCY_IN_PROGRESS`；否则 `REPLAY`。
- **命名空间互不相见**：别的用户、服务或 system 名下同一个键的行都看不见；结果是 `EXECUTE`，不透露这个键在别处存在。
- **请求头与 body**：相同，或只出现一个 → 用它；两个都有且不同 → 400 `IDEMPOTENCY_MISMATCH`。

## 错误

| 错误类 | 线上 |
|---|---|
| `JSON_INVALID` | `INVALID_ARGUMENT`（请求体不是可接受的 JSON） |
| `IDEMPOTENCY_MISMATCH` | 400 / `INVALID_ARGUMENT`，平台 reason |
| `IDEMPOTENCY_IN_PROGRESS` | 409 / `ABORTED`，平台 reason（出现在 `decide` 的 `REJECT` 里） |

## 本处补定的口径

请评审：JSON 重复成员名一律拒收，而不是"后者为准"；不一致先于"进行中"报告；过期是半开区间（`now == expires_at` 已经算新键）；`svc:` 与 `system` 命名空间照 P13.1，服务账号 token（`sub: svc:…`，P5.7）在有签发方之前不在范围内。键本身的格式（长度、字符集）协议没有定，暂无向量。

## 重新生成

`python3 gen/gen_idempotency.py`；交叉验证用 Node 加 npm 包 `canonicalize`（见 [..](../README.zh.md) 的 `make xcheck`）。生成器写文件之前先断言 RFC 8785 的样例表（§3.2.2.3 数字、§3.2.3 排序、§3.2.4 示例）。
