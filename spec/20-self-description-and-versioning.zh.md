[English](20-self-description-and-versioning.md) · [中文](20-self-description-and-versioning.zh.md)

# P20 自描述与协议版本

组件怎么说明它实现了哪个协议版本、用什么构建、提供什么，以及协议本身怎么变化。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P20.1 | —（本仓库自身的规则） | 协议版本是 `MAJOR.MINOR`。minor 版本只增加**可选**的面：新的能力位，新的可选端点、字段、头、键或 reason；它从不改变同一 major 里更早版本所定义内容的含义。变成必需的行为只出现在新的 major 里 | — |
| P20.2 | MUST | 组件在 `assembly.yaml` 里声明 `protocol: "<MAJOR.MINOR>"`（[schema](../schemas/assembly-protocol.schema.json)），并按那个版本的用例集测试。套件为每个 minor 保留一份用例集；旧组件永远按它声明的版本测试。不是用官方 SDK 写的组件还要声明 `language: <name>` | CP-CORE-11 |
| P20.3 | MUST | SDK 在它的 README 和 `/_be/info` 里写明它实现的协议版本 | CP-CORE-11 |
| P20.4 | MUST | 主端口上的 `GET /_be/info`：从不经边缘路由，不鉴权，不含密钥值。它的响应体符合 [`info.schema.json`](../schemas/info.schema.json)，并与镜像的清单（ID、版本、端口）一致 | CP-CORE-11 |

## `/_be/info`

```json
{
  "component_id": "erp/sales",
  "component_version": "3.0.0",
  "protocol": "1.0",
  "sdk": { "name": "be-sdk-go", "version": "0.6.0" },
  "language": { "name": "go", "version": "1.25.11" },
  "profiles": ["core", "auth", "scope", "grpc", "outbound", "events-pub", "events-sub", "idempotency", "db", "jobs", "lifecycle"],
  "ports": { "http": 8085, "grpc": 9095 },
  "migrations": { "component": "0001", "platform": 1 },
  "members": null
}
```

| 字段 | 含义 |
|---|---|
| `component_id`、`component_version` | 等于 `COMPONENT_ID` 和 `COMPONENT_VERSION` |
| `protocol` | 实现的版本，等于 `assembly.yaml` 的 `protocol` |
| `sdk` | 官方 SDK 及其版本；没有官方 SDK 的组件为 `null` |
| `language` | 语言及其运行时版本 |
| `profiles` | 组件声称的 profile；套件把它们和自己从清单里选出的 profile 对比 |
| `ports` | `http` = 主端口，另外每个额外端口按名字列出 |
| `migrations.component` | 镜像里已应用的最新组件迁移；`migrations.platform` 是平台迁移版本（`besdk_platform_version`） |
| `tzdata` | 可选：运行时自带的 IANA 时区数据版本，例如 `2026c`（[P11.7](11-migrations-and-data-shapes.zh.md)） |
| `degraded` | 可选：启动时决定以降级模式运行的部分，例如没装 `mdm/org` 时的 `calendar`（[P11.9](11-migrations-and-data-shapes.zh.md)）；没有降级时不出现或为空 |
| `members` | 组件为 `null`；外壳上是成员对象的数组，形状相同，只是没有 `members` |

## 说明

- 套件先读 `/_be/info`，在运行任何 profile 之前，拿它和容器及清单核对。
- 要求 ID 和用例 ID 跨版本稳定（[00-reading-the-spec](00-reading-the-spec.zh.md#标识)）。
