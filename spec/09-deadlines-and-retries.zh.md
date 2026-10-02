[English](09-deadlines-and-retries.md) · [中文](09-deadlines-and-retries.zh.md)

# P9 截止时间与重试预算

每个请求都有截止时间，而且它在传递中只会缩短：每一跳给子调用的时间都少于自己拥有的时间。本章陈述这条规则，并逐跳汇总其它章定义的默认值；某一行与其来源章不一致时，以来源章为准。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P9.1 | MUST | 子调用的超时短于当前工作单元自己的调用方仍愿意等它的时间。没有任何一层延长它收到的截止时间 | CP-OUT-02, CP-OUT-07 |
| P9.2 | MUST | 只有一层重试。组件代码从不在已经会重试的运行时调用外面再套一层重试循环；更高一层的重试（reconciler、重投的事件、前端重试）复用同一个幂等键 | —（组件代码中为 INTERNAL） |

## 逐跳预算

| 跳 | 默认 | 来源 |
|---|---|---|
| 边缘 | 路由截止时间 + 5 s | 边缘配置，与路由出自同一处声明（[P3.13](03-http-surface.zh.md)） |
| 入站 HTTP | `HTTP_DEFAULT_TIMEOUT`（10 s）；声明为编排的路由 15 s | [P3.4](03-http-surface.zh.md) |
| HTTP 服务端 | 读请求头 5 s，读 30 s，写 = 路由截止时间 + 5 s，空闲 120 s | [P3.5](03-http-surface.zh.md) |
| 入站 gRPC | 调用方的 `grpc-timeout`；没带时 10 s | [P7.4](07-system-rpc.zh.md) |
| 出站 gRPC 和用户面 HTTP | `min(3 s, remaining − 50 ms)`；不足 50 ms 时不发出 | [P7.7](07-system-rpc.zh.md), [P8.2](08-outbound-http.zh.md) |
| 第三方 HTTP | 10 s，按客户端 | [P8.3](08-outbound-http.zh.md) |
| SQL 语句 | `min(5 s, remaining)` | [P10.3](10-database.zh.md) |
| 锁等待 | 2 s | [P10.3](10-database.zh.md) |
| 事务里空闲 | 30 s | [P10.3](10-database.zh.md) |
| 事件 handler | ack wait（30 s）− 5 s | [P12.9](12-events.zh.md) |
| Job 单次运行、reconciler 单步 | job 声明的超时（必填） | [P14](14-background-jobs.zh.md) |
| 取连接 | `min(PG_POOL_ACQUIRE_TIMEOUT, remaining)` | [P10.5](10-database.zh.md) |

## 逐层重试

| 层 | 重试什么 | 上限 | 来源 |
|---|---|---|---|
| 数据库事务 | SQLSTATE `40001`、`40P01` | 3 次尝试，`10 ms · 2^n` 加抖动 | [P10.4](10-database.zh.md) |
| gRPC，幂等方法 | `UNAVAILABLE` | 总共 3 次尝试（首次 + 2 次重试）；靠 `retryThrottling` 让稳态下的重试流量 ≤ 10 % | [P7.8](07-system-rpc.zh.md) |
| gRPC，其它方法 | 只有透明重试 | 一次 | [P7.8](07-system-rpc.zh.md) |
| 用户面 HTTP | 连接被重置时的 `GET` | 一次 | [P8.2](08-outbound-http.zh.md) |
| 事件 | handler 出错 | `EVENTS_MAX_DELIVER`（8），然后进死信 | [P12.7](12-events.zh.md) |
| 排队的 job | handler 出错 | worker 的最大尝试次数，然后 `dead` | [P14](14-background-jobs.zh.md) |
| reconciler | handler 出错 | reconciler 的上限，然后放弃 | [P14](14-background-jobs.zh.md) |

## 舱壁

| 资源 | 上限 | 达到时 |
|---|---|---|
| 每个（成员，依赖）的并发出站调用 | 64 | 立即 `RESOURCE_EXHAUSTED` / `OUTBOUND_LIMIT` |
| 每个成员的数据库连接 | `PG_POOL_MAX` | 等待，然后 `RESOURCE_EXHAUSTED` / `DB_POOL_EXHAUSTED` |
| 每个订阅同时处理的消息 | 4；每个 durable 最多 256 条未确认 | broker 暂缓投递 |

## 说明

- 嵌套重试会相乘：三层各三次尝试，故障期间最底层就是 27 次调用，恰好发生在依赖最扛不住的时候。这就是 P9.2 存在的原因。
- 舱壁和截止时间取代熔断器。
