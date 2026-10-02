[English](08-outbound-http.md) · [中文](08-outbound-http.zh.md)

# P8 出站 HTTP：用户面与第三方

gRPC 之外的两类出站 HTTP：代表当前用户调用另一个组件的 REST 用户面，以及调用第三方（钉钉、Casdoor 这类）。外加一条规则：事务里不发生网络调用。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P8.1 | MUST | 调用另一个组件的用户面 HTTP，只在上下文里有用户时发出。它原样转发调用者原始的 `Authorization` 头，以及存在时的 `X-Request-Id`、`traceparent`、`tracestate`、`baggage` 和 `X-Authz-Revision`。上下文里没有用户时（事件 handler、job、gRPC 系统调用），以 `UNAUTHENTICATED` 失败；从不悄悄换成系统身份 | CP-OUT-06 |
| P8.2 | MUST | 用户面 HTTP 使用 [P7.7](07-system-rpc.zh.md) 的出站截止时间和 [P7.9](07-system-rpc.zh.md) 的舱壁。只有 `GET` 会重试，只重试一次，且只在连接被重置时。对方回的 problem+json 被还原成同样的状态码、`reason` 和 `domain` | CP-OUT-06 |
| P8.3 | MUST | 第三方 HTTP：默认超时 10 s，可以按具名客户端用组件自己的配置键配置；有追踪，并计入 `be_http_client_requests_total` / `be_http_client_duration_seconds`（标签 `target` = 客户端名、`method`、`status_code`）；用户面 HTTP（P8.1）计入同一对指标，`target` = 依赖的组件 ID。它**不转发**任何内部头：不转发 `Authorization`、`be-*`、`X-Authz-*`、`X-Request-Id`。可以发送 W3C `traceparent` | — |
| P8.4 | INTERNAL | 事务里不走网络：当前工作单元持有打开的事务时，运行时提供的每一种出站调用（gRPC、用户面 HTTP、第三方 HTTP、直接发布到总线）都拒绝开始，以 `INTERNAL` 失败；在测试构建里直接中止测试。从事务里引起外部效果只有两条路：一行 outbox（[P12.1](12-events.zh.md)）和一个排队的 job（[P14](14-background-jobs.zh.md)） | — |

## 说明

- P8.1 是 [P7.1](07-system-rpc.zh.md) 在用户面的那一半：按用户范围过滤的数据，用用户自己的 token 读取，于是由被调方按自己的规则判定。
- P8.4 的事务守卫跟着调用的上下文走，不跟着进程走，所以在外壳里按成员生效。
- `be_http_client_requests_total` / `be_http_client_duration_seconds` 这一对指标也列在 [P18.3](18-observability.zh.md) 中。
