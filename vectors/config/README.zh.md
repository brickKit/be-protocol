[English](README.md) · [中文](README.zh.md)

# 语义向量：config

组件启动时怎么解析配置、依赖地址变量与槽位族地址怎么命名和读取、密钥文件怎么读、组件可以声明哪些键名以及密钥怎么声明、`config/*.yaml` 里能用哪些取值写法（协议 P2；foundations 24；brickKit 的环境变量契约）。对应 SDK API：Go 的 `Runtime.Config`（类型化读取、`Endpoint(dep, port)`、槽位族地址）与密钥源；`forms.json` 给 be-ops 和门禁用，不给 SDK。

## 文件

| 文件 | 用例数 | 操作 |
|---|---|---|
| `values.json` | 104 | `parse_value`、`read_undeclared`、`secret_text` |
| `endpoints.json` | 31 | `endpoint_name`、`endpoint_value`、`family_address` |
| `keys.json` | 29 | `key_name`、`key_declaration` |
| `forms.json` | 32 | `value_form` |

## 操作

| 操作 | 输入 | 期望 |
|---|---|---|
| `parse_value` | `type`（`string`、`integer`、`boolean`、`duration`、`duration_list`、`url`、`json`、`enum`）、`value`（环境变量的值；`null` = 变量不存在），可选 `default`、`required`、`secret`、`minimum`、`schemes`、`json_kind`、`enum` | `set: false`，或 `set: true` 加 `value`；`secret: true` 时为 `source: file` 加 `path`（变量里是文件路径，P2.7） |
| `read_undeclared` | `key`、`declared[]` | 平台名为 `allowed: true` |
| `secret_text` | `content`（密钥文件的文本）、`required` | `set: false`，或 `set: true` 加 `value`（P2.9） |
| `endpoint_name` | `dependency`、`port`（`""` 表示主端口） | 注入变量的 `name` |
| `endpoint_value` | `value`（或 `null`） | `present: false`，或 `present: true` 加 `address`（`host:port`） |
| `family_address` | `key`（`AUTHZ_URL`、`AUTHZ_GRPC_URL`、`IAM_URL`、`IAM_GRPC_URL`）、`value`（或 `null`） | `present: false`，或 `present: true`：`*_URL` 键加 `base`（`http://host:port`，REST 路径直接拼在后面），`*_GRPC_URL` 键加 `target`（`host:port`，gRPC 拨号目标），P2.10 |
| `key_name` | `key` | `valid: true` |
| `key_declaration` | `key`，可选 `secret`、`mount`、`type`（`configSchema` 的一项） | `valid: true`（P2.12） |
| `value_form` | `written`（字符串或 `{existingSecret, key}`）、`secret` | `form`：`literal`、`var`、`env`（带 `name`，可选 `default`）、`template`（带 `names`）、`file`（带 `path`）、`existing_secret`、`endpoint`（带 `component`，可选 `version`、`port`、`path`） |

## 规则

- **有没有**：变量不存在时取 `default`；必填则 `CONFIG_MISSING`；否则为未设置。除 `string` 外，空值一律算未设置（对应 brickKit 的 `${NAME:-}`）。值存在却解析不了是 `CONFIG_INVALID`，永不回退到默认值；默认值本身解析不了也是错误。
- **integer**：`^-?[0-9]+$`（前导零按十进制），范围 ±(2^53−1)，保证每门语言都能精确表示；不接受 `+`、空格、分隔符、十六进制、指数、非 ASCII 数字。
- **boolean**：恰好 `true`、`false`、`1`、`0`。
- **duration**：Go `time.ParseDuration` 的语法（`5s`、`1h30m`、`1.5h`、`200ms`、`10us` / `10µs` / `10μs`、`7ns`、`.5s`、`+5s`、单独的 `0`）；没有"天"单位，不接受大写、空格、ISO 8601；负时长拒收。值以纳秒计，写成十进制字符串。
- **duration_list**：逗号分隔的时长，不带空格，不能有空元素，每个都为正（`EVENTS_BACKOFF`）。
- **url**：`scheme://host[:port][path]`，scheme 小写，只有一个主机，端口 1–65535，无空白；`schemes` 限定某个键可用的 scheme（`EVENT_BUS_URL`：`nats`、`postgres`、`kafka`）。值原样返回。
- **json**：按 I-JSON（重复成员名和 `NaN` 拒收）；`json_kind` 要求对象或数组（`JOBS_OVERRIDES` 是对象）。
- **enum**：精确匹配，区分大小写（`LOG_LEVEL`）。
- **密钥**：`secret: true` 的键声明 `mount: file`、名字以 `_FILE` 结尾；变量里是 brickKit 挂进来的文件的**绝对路径**（`/run/brickkit/secrets/<服务名>/<键>`，`mode: local` 时是宿主机路径）；相对路径、目录或直接给值都是 `CONFIG_INVALID`。文件的文本去掉恰好一个末尾 LF 或 CRLF 就是值（`secret_text`）；结果为空算未设置（必填则 `CONFIG_MISSING`）。文件变了运行时会重读（P2.9）。非密钥键里的路径只是普通文本。
- **未声明的键**：读一个既没在 `configSchema` 声明、也不是平台名（`COMPONENT_ID`、`COMPONENT_VERSION`、`PORT`、`*_ENDPOINT`）的键，是 `CONFIG_UNDECLARED`。
- **地址变量**：`<依赖 id 转大写，/ 和 - 换成 _>[_<端口名>]_ENDPOINT`。没装的可选依赖根本没有这个变量（`present: false`）；值为空是配置错误。值的形式是 `http://host:port[/]`，SDK 去掉 `http://` 和末尾的 `/`；其它形式是 `CONFIG_INVALID`。
- **槽位族地址**：`AUTHZ_URL`、`AUTHZ_GRPC_URL`、`IAM_URL`、`IAM_GRPC_URL` 里是 `$endpoint:` 写出的值，`http://host:port`，不带路径（末尾的 `/` 去掉）；`*_GRPC_URL` 的值去掉 `http://` 就是 gRPC 目标。gRPC 端口从不由 HTTP 端口推算。族成员这次不跑时该键不存在（`present: false`）。
- **键名**：`^[A-Z][A-Z0-9_]*$`；`COMPONENT_ID`、`COMPONENT_VERSION`、`PORT`、`BRICKKIT_SERVED_MEMBERS*` 和所有 `*_ENDPOINT` 归平台。
- **密钥的声明**：`secret: true` ⇔ `mount: file` ⇔ 名字以 `_FILE` 结尾。先满足 brickKit 自己的规则：`mount` 只能是 `file`，只能和 `secret: true` 一起写，只能用于 `string`。
- **取值写法**（be-ops、门禁）：`$var:NAME` 必须是整个值；`${NAME}` 或 `${NAME:-default}`（引用不能嵌套）；模板里可以嵌 `${NAME}`；`file://` 路径相对于项目根且不能跳出项目；`existingSecret` 只用于 `secret: true` 的项；`$endpoint:<scope>/<name>[@<x.y.z>][:<端口名>][/<路径>]` 必须是整个值，不能用于密钥（版本在端口之前，名字之后的第一个 `/` 开始路径）。**密钥只能是引用**：`secret: true` 的项写成字面量、模板或带非空明文默认值，一律拒收。

## 错误

| 错误类 | 何时 |
|---|---|
| `CONFIG_MISSING`、`CONFIG_INVALID`、`CONFIG_UNDECLARED` | 启动时：退出码 78，一行 JSON 日志点名该键（P1.2）；外壳里先收齐全部成员的错误 |
| `COMPONENT_INVALID`、`PORT_NAME_INVALID` | 依赖 id 或端口名格式不对 |
| `CONFIG_KEY_INVALID`、`CONFIG_KEY_RESERVED` | 组件不能声明的键（门禁）；按别的键名去读槽位族地址也是 `CONFIG_KEY_INVALID` |
| `SECRET_NOT_FILE`、`FILE_SUFFIX_REQUIRED`、`FILE_SUFFIX_RESERVED`、`MOUNT_INVALID`、`MOUNT_NEEDS_SECRET`、`MOUNT_NEEDS_STRING` | 密钥没按 P2.12 声明（门禁） |
| `FORM_INVALID`、`FORM_NOT_FOR_PLAIN`、`SECRET_NOT_REFERENCE`、`SECRET_PLAINTEXT_DEFAULT` | 项目不接受的取值写法（门禁） |

## 本处补定的口径

请评审：类型化的键空值算未设置；整数限定在 ±(2^53−1)；布尔只认 `true` / `false` / `1` / `0`（不是 Go `ParseBool` 那一大套）；负时长拒收；时长列表不许空格；地址变量不是 `http://host:port[/]` 就拒收；密钥写成模板或带明文默认值都拒收；密钥文件只去掉一个末尾换行；`_FILE` 后缀留给以文件交付的密钥。

## 重新生成

`python3 gen/gen_config.py`；交叉验证 `go run gen/xcheck_config.go .`（它还会打印 Go 自带函数比协议宽的地方）。
