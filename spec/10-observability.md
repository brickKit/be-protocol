# 10 观测输出

依据：装配项目协议 17 的“观测”（两档共享的输出契约、脱敏）、组件间调用与错误的日志级别（[03](03-errors.md) 的 P3.9）。本章把日志与指标写成从外部可以逐项检验的形状，使不同语言的组件在同一个看板、同一条检索里可以比较。协议 17 表中的业务健康指标（发件表最老年龄、消费者落后、审计未转运……）随各自的章节加入。

## 日志

| 编号 | 层级 | 规则 | 检验 |
| --- | --- | --- | --- |
| P10.1 | 必须 | 运行日志写到标准输出，每行一个 JSON 对象（UTF-8），不跨行；外壳中全部成员与外壳自己写同一输出 | CK-OBS-01 |
| P10.2 | 必须 | 每行至少有：`time`（RFC 3339，UTC，以 `Z` 结尾，至少到毫秒）、`level`（`DEBUG`、`INFO`、`WARN`、`ERROR` 之一）、`msg`（非空）、`component`（组件 ID；外壳自己的行写外壳 ID）、`version`。请求或调用范围内的行另有 `request_id` 与 `trace_id`（32 位小写十六进制） | CK-OBS-01 |
| P10.3 | 必须 | 每个用户面请求与系统面调用写一行访问日志：`msg` 为 `access`；HTTP 带 `method`、`route`（路由模板，不是实际路径）、`status`、`duration_ms`；gRPC 带 `method`（完整方法名）、`code`（gRPC 码名）、`duration_ms`；级别按 P3.9。平台端点不写 INFO 级的访问日志（P1.7） | CK-OBS-02 |
| P10.4 | 必须 | 日志从不包含凭据与密钥的值：请求的 `Authorization` 头、令牌、密码、密钥文件的内容（P8.3；协议 17 的脱敏） | CK-OBS-03 |

## 指标

| 编号 | 层级 | 规则 | 检验 |
| --- | --- | --- | --- |
| P10.5 | 必须 | 用户面端口的 `GET /metrics` 以 Prometheus 文本格式回答，不经过认证与授权（与 P1.7 的平台端点相同）；只有这个组件（外壳：全部成员）自己的指标 | CK-OBS-04 |
| P10.6 | 必须 | 至少有下表的指标族，名称、类型与标签一字不差；直方图的上界是 0.005、0.01、0.025、0.05、0.1、0.25、0.5、1、2.5、5、10 秒（加 `+Inf`），各语言相同才能在同一看板比较 | CK-OBS-04 |
| P10.7 | 必须 | 外壳的 `/metrics` 汇集全部成员，每个序列带 `component` 标签（成员的组件 ID） | CK-OBS-05 |

| 指标族 | 类型 | 标签 | 何时有序列 |
| --- | --- | --- | --- |
| `be_http_server_duration_seconds` | 直方图 | `method`、`route`（路由模板）、`status` | 用户面处理过请求之后 |
| `be_grpc_server_duration_seconds` | 直方图 | `method`（完整方法名）、`code` | 系统面处理过调用之后（有系统面的组件） |
| `be_outbound_attempts_total` | 计数 | `dependency`（组件 ID）、`surface`（`http`、`grpc`）、`class`（[04](04-calls.md) 的结果分类） | 发起过出站调用之后 |
| `be_outbound_rejected_total` | 计数 | `dependency`、`surface`、`reason`（没有发出的原因） | 有调用没有发出之后 |
| `be_outbound_breaker_open` | 计量 | `dependency`、`surface` | 熔断器不处于关闭时为 1，否则为 0 |

## 检查清单

| 检查 | 内容 |
| --- | --- |
| CK-OBS-01 | 组件运行期间（启动、处理请求与调用、停止）输出的每一行都是带必需字段的 JSON 对象；请求范围的行带合格的 `request_id` 与 `trace_id` |
| CK-OBS-02 | 每个请求与调用恰好一行访问日志，字段齐全；健康、就绪、自描述与指标端点不写 INFO 级访问日志 |
| CK-OBS-03 | 带已知令牌的请求、已知的数据库密码与密钥文件内容，都不出现在输出中 |
| CK-OBS-04 | `/metrics` 能按 Prometheus 文本格式解析；处理过请求后必需的指标族存在，类型、标签与直方图上界正确 |
| CK-OBS-05 | 外壳的 `/metrics` 中每个序列带成员的 `component` 标签 |
