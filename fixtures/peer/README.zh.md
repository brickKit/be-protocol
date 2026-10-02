[English](README.md) · [中文](README.zh.md)

# 夹具：peer

`conformance/peer` 是 widget 夹具的依赖。它只有契约、没有实现：组件一致性套件的假对端按 `contracts/conformance/peer/v1/peer.proto` 应答它的 gRPC 方法，按 `contracts/peer.openapi.yaml` 应答它唯一的 HTTP 操作，回答内容取自 widget 的 `conformance/fixtures.yaml`，并且能让任何一个方法挂起、变慢或失败。它记录收到的一切（metadata、截止时间、连接、请求头），出站类用例就是靠这些观察 widget 的。

## 接口

| 面 | 操作 | widget 用它做什么 |
|---|---|---|
| gRPC | `Reserve`（`IDEMPOTENT`） | 审批第 2 步 |
| gRPC | `GetReservationStatus`（`NO_SIDE_EFFECTS`） | 调和器；`slow?via=peer` |
| gRPC | `BatchGetOwners`、`ListOwners`（`NO_SIDE_EFFECTS`） | owner 快照（读穿透、回填） |
| gRPC | `Notify`（`IDEMPOTENT`） | 队列作业 `widget.notify` |
| HTTP | `GET /conformance/peer/owners/{owner_id}` | `GET /conformance/widget/widgets/{id}/owner`（UserHTTP） |
| 事件 | `conformance.owner.updated.v1`、`conformance.reservation.expired.v1` | 由套件代 peer 发布 |
| 错误 | `QUOTA_EXCEEDED`（`FAILED_PRECONDITION`） | widget 原样转达，domain 为 `conformance/peer` |
