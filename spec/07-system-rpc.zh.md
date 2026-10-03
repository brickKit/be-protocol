[English](07-system-rpc.md) · [中文](07-system-rpc.zh.md)

# P7 系统面：组件之间的 gRPC

gRPC 是组件之间的系统协议：出站调用带什么、服务端强制什么、连接复用、截止时间、重试、舱壁和批量上限。系统面上的每个调用方都是系统主体；按用户范围过滤的数据，只经 REST 读写（[P8](08-outbound-http.zh.md)）。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P7.1 | MUST | gRPC 是系统协议：从不经边缘路由，从不列入 `edge_routes`。用户请求要读别的组件按范围过滤的数据时，走用户面（[P8.1](08-outbound-http.zh.md)）。允许三类 rpc：`data_scopes: none` 的数据（主数据）；系统协议（预留、确认、取消；创建任务；检查会计期间）；按 ID 补全（`BatchGet`），ID 是调用方已经持有的 | — |
| P7.2 | MUST | 每次调用都带的出站 metadata：`traceparent`、`tracestate`、`baggage`（W3C）；`x-request-id`；**`be-caller`** = 调用方组件的 ID（在外壳里是调用方成员的 ID），总是携带；`be-actor-sub` = 引发这次调用的那个请求的用户的平台 `sub`，**在调用时**从上下文读取，后台工作不带；`be-actor-act` = token 的 `act` 链，存在时以 JSON 形式携带。入站调用缺 `be-caller` 时，答 `UNAUTHENTICATED`，reason 为 `MISSING_CALLER` | CP-RPC-01, CP-RPC-02, CP-OUT-08 |
| P7.3 | MUST | 服务端把每次调用标成系统主体 `{caller, actor_sub, act}`。`be-caller` 和 `be-actor-*` 只被记录（日志、审计），从不用来授予访问权限。契约里保留下来的面向用户的 rpc，在任何组件代码运行之前就由运行时答 `UNAUTHENTICATED`；从不答 `INTERNAL`，也从不崩溃 | CP-RPC-03 |
| P7.4 | MUST，顺序 INTERNAL | 服务端拦截器，一元和流式相同，顺序为：panic 恢复 → 身份 → 截止时间下限（调用方没发 `grpc-timeout` 时为 10 s）→ 批量上限（P7.10）→ 错误详情规范化（[P4.2](04-errors.zh.md)）→ RED 指标 → 追踪 | CP-RPC-02 |
| P7.5 | MUST | 服务端参数：最大接收消息大小显式设为 4 MiB；`MaxConnectionAge` = `GRPC_MAX_CONNECTION_AGE`（默认 5 min），`MaxConnectionAgeGrace` 30 s，它**必须**长于服务端接受的最长截止时间（P7.4 的 10 s 下限、路由声明的截止时间），这样 `GOAWAY` 永远不会切断已接纳的调用；keepalive 强制策略 `MinTime` 20 s，拒绝没有活动调用时的 ping，前提是服务端库能强制（grpc-js 没有这个设置：做不到的运行时在 README 里写明，并依赖客户端遵守 P7.6）。外壳里每个成员都有自己的服务端，监听自己的端口 | CP-RPC-04, CP-RPC-05 |
| P7.6 | MUST | 客户端连接按（成员，依赖，端口）复用，懒建，停止时关闭：稳态下每个依赖一条 TCP 连接。keepalive：活动调用空闲 30 s 后发 ping，超时 10 s，没有活动调用时不发 ping。地址是去掉 scheme 的 `<DEP>_GRPC_ENDPOINT`（[P2.6](02-configuration.zh.md)），槽位族则是按同样方法读取的 `*_GRPC_URL`（[P2.10](02-configuration.zh.md)）。建立连接时不捕获任何与用户有关的东西 | CP-OUT-01 |
| P7.7 | MUST | 出站截止时间：`min(3 s, remaining − 50 ms)`。剩余不足 50 ms 时不发出调用，以 `DEADLINE_EXCEEDED` / `DEADLINE_BUDGET_EXHAUSTED` 失败。确实需要更长时间的系统 rpc 用方法选项声明（已预留，1.0 中未定义） | CP-OUT-02 |
| P7.8 | MUST | 重试由契约决定：`idempotency_level` 为 `NO_SIDE_EFFECTS` 或 `IDEMPOTENT` 的方法只在 `UNAVAILABLE` 时重试：`maxAttempts` 总共 3 次（首次尝试加最多 2 次重试），退避初始 50 ms、上限 500 ms、倍数 2。其它方法只有 gRPC 的透明重试（请求从未离开客户端时）。重试预算是 `retryThrottling {maxTokens: 10, tokenRatio: 0.1}`，"重试流量 ≤ 10 %" 是它的稳态上限，不是硬上限。预算的作用范围取决于 gRPC 库，每个运行时都要写明：Go 和 Python 按客户端 channel 计算（每个成员、依赖和端口一个，P7.6），所以一个成员的重试从不花掉另一个成员的预算，并在 channel 的 resolver 更新时（通常在一次 `GOAWAY` 之后）补满；grpc-js 按进程和目标计算，重新解析时不补满，所以在 TypeScript 外壳里调同一个依赖的成员共用一份预算。hedging 关闭。请求里有 `idempotency_key` 字段的每个 rpc 都声明 `idempotency_level = IDEMPOTENT`（门禁 `idempotency-level-scan`） | CP-OUT-03, CP-OUT-04 |
| P7.9 | MUST | 出站舱壁：每个（成员，依赖）最多 64 个并发调用。第 65 个立即以 `RESOURCE_EXHAUSTED` / `OUTBOUND_LIMIT` 失败；调用从不排队 | CP-OUT-05 |
| P7.10 | MUST | 批量上限：ID 的 repeated 字段用字段选项 `(be.v1.max_items) = N` 声明上限（[`proto/be/v1/limits.proto`](../proto/be/v1/limits.proto)）；没写时上限为 500。更大的请求答 `INVALID_ARGUMENT`，带 `ErrorInfo{reason: BATCH_TOO_LARGE, metadata: {field, max, got}}` 和 `BadRequest`。调用方把大集合切成不超过上限的分片。`be.*` 包里的每个自定义选项，其**短名在组件 proto 能看到的所有选项中唯一**（有些生成器，包括 ts-proto，只按短名、不带包名暴露选项）：`max_items` 已被占用，以后的选项永不重用任何选项的短名，不论是我们的还是别的包的。每个官方 SDK 都带上 `be/v1/limits.proto` 的生成代码（Python：可导入的 `be.v1.limits_pb2`），组件的生成代码只链接这一份 | CP-RPC-06 |
| P7.11 | MUST | 不用流式 rpc。不压缩，但超过 1 MiB 的响应可以按调用用 gzip 压缩。proto 包名为 `<domain>.<name>.v<n>`，只通过新增来变更（`buf breaking`） | — |
| P7.12 | MUST | 客户端拦截器，顺序为：默认截止时间（P7.7）→ 出站舱壁（P7.9）→ metadata（P7.2）→ 客户端 RED 指标 → 事务守卫（[P8.4](08-outbound-http.zh.md)） | —（顺序 INTERNAL） |
| P7.13 | MUST | 每个方法都声明 `option idempotency_level`：读、`BatchGet` 和 `GetStatus` 用 `NO_SIDE_EFFECTS`；每个接受 `idempotency_key` 的写用 `IDEMPOTENT`。每个聚合根都提供 `BatchGet`；每个跨组件写都提供按幂等键查询的 `GetStatus`（[P13](13-idempotency.zh.md)） | —（门禁） |
| P7.14 | MUST | 端口在 `component.yaml` 里说明它讲什么协议：主端口 `deployment.protocol: http`，名为 `grpc` 的额外端口 `protocol: grpc`（其它额外端口写各自的协议，`http`、`grpc` 或 `tcp`）。brickKit 把它写成 Kubernetes Service 端口的 `appProtocol`（部署文件的 `k8s.appProtocols` 可以按集群认的词改名），这样读它的服务网格或网关就按请求、而不是按连接来均衡 gRPC；它在 Docker / Podman 上什么都不改，也不改注入的地址。没有网格时，`MaxConnectionAge`（P7.5）仍是起作用的均衡手段 | CP-CORE-12 |

## metadata

| 键 | 值 | 谁设置 |
|---|---|---|
| `grpc-timeout` | 调用方的剩余预算（P7.7） | 调用方运行时 |
| `traceparent`, `tracestate`, `baggage` | W3C 追踪上下文 | 调用方运行时 |
| `x-request-id` | 入站请求的 ID，或一个新 ID | 调用方运行时 |
| `be-caller` | 调用方组件或成员的 ID | 调用方运行时 |
| `be-actor-sub` | 用户的平台 `sub`，在调用时读取 | 调用方运行时 |
| `be-actor-act` | `act` 链，JSON | 调用方运行时 |
| `authorization` | 预留给跨信任边界的服务 token（`sub: svc:<id>`） | — |

## 服务配置

每个运行时为依赖的可重试方法生成的服务配置；这段 JSON 在每门语言里完全相同：

```json
{
  "methodConfig": [{
    "name": [{ "service": "erp.inventory.v1.InventoryService", "method": "GetReservationStatus" }],
    "retryPolicy": {
      "maxAttempts": 3,
      "initialBackoff": "0.05s",
      "maxBackoff": "0.5s",
      "backoffMultiplier": 2,
      "retryableStatusCodes": ["UNAVAILABLE"]
    }
  }],
  "retryThrottling": { "maxTokens": 10, "tokenRatio": 0.1 }
}
```

## 说明

- `MaxConnectionAge` 是在 Kubernetes 上分摊负载的手段：kube-proxy 按 TCP 连接做均衡，复用的 HTTP/2 连接会一直停在一个 pod 上；每五分钟一次 `GOAWAY`，让客户端重新连接到重新选出的 pod。
- 同一外壳的成员之间经网络互相调用，与单跑时完全一样（[P19.2](19-shells.zh.md)）；没有进程内传输。
