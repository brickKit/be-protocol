[English](13-idempotency.md) · [中文](13-idempotency.zh.md)

# P13 命令幂等

带幂等键的写命令怎么认领、绑定、重放和过期，REST 和 gRPC 一样。表：`besdk_idempotency`（[ddl/](../ddl/)）。指纹向量：`vectors/idempotency/`。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P13.1 | MUST | 每个有副作用的写命令都接受幂等键（REST 上是 [P3.7](03-http-surface.zh.md)；gRPC 上是请求字段 `idempotency_key`）。键在一个 **caller 命名空间**里生效：用户请求是 `user:<sub>`，系统调用是 `svc:<be-caller>`，本组件自己的后台工作是 `system` | CP-IDEM-01, CP-IDEM-06 |
| P13.2 | MUST | 键绑定三样东西：`command`（权限键，或 rpc 全名）、`target`（命令作用的聚合 ID；建类命令为空）和 `request_hash`（为该命令声明的指纹字段按 RFC 8785 JCS 规范化后的 SHA-256）。同一个 caller、同一个键，command、target 或 hash 不同时，答 `400` / `INVALID_ARGUMENT`，reason 为 `IDEMPOTENCY_MISMATCH` | CP-IDEM-02, CP-IDEM-03, CP-IDEM-04 |
| P13.3 | MUST | 已认领但未完成的键（两段式命令：认领、一次网络调用、然后完成）答 `409` / `ABORTED`，reason 为 `IDEMPOTENCY_IN_PROGRESS`。已完成的键重放存储的结果，状态码相同，不再执行。确定失败的步骤释放认领，所以同一个键可以重试 | CP-IDEM-01, CP-IDEM-05 |
| P13.4 | MUST | 不同 caller 用同一个键互相独立：谁也看不到对方的结果，任何应答都不透露该键存在于另一个命名空间 | CP-IDEM-06 |
| P13.5 | MUST | 检查顺序固定：校验参数 → 对 target 授权并检查数据范围 → 查找或认领键 → 校验状态机 → 写入。重放的建类命令，通过组件自己带范围的读取读回；超出范围时的应答与 mismatch 相同 | CP-IDEM-02 |
| P13.6 | MUST | 同一 caller、同一键的并发请求只执行一次；其它请求拿到重放结果或 `IDEMPOTENCY_IN_PROGRESS`。认领是原子的（[P10.9](10-database.zh.md)） | CP-IDEM-07 |
| P13.7 | MUST | 键从首次使用起 **30 天**内有效（`expires_at = created_at + 30 days`）；之后同一个键就是一个新命令。运行时删除过期行。每个带键的命令契约都写明这 30 天 | — |
| P13.8 | MUST | 调用另一个组件写命令的事件 handler，使用从事件确定性派生的键（`crm-won:<opportunity_id>`），落在 `svc:` 命名空间，这样一次重投就是同一个命令的重试 | — |
| P13.9 | MUST | 跨组件写的每个被调方都提供按幂等键查询的 `GetStatus`；超时后，调用方在补偿之前先查询 | — |

## 指纹

1. 取命令声明为指纹的请求字段（业务字段；从不包括键本身，从不包括传输头）。
2. 把它们序列化成一个 JSON 对象，用 RFC 8785（JCS）规范化。
3. `request_hash` = UTF-8 字节的 SHA-256；以 32 个原始字节（`BYTEA`）存储。

## 认领语句

```sql
-- a new claim returns its status; a key that is already taken returns no row
INSERT INTO besdk_idempotency (caller, idempotency_key, command, target, request_hash, status, expires_at)
VALUES ($1, $2, $3, $4, $5, 'CLAIMED', now() + interval '30 days')
ON CONFLICT (caller, idempotency_key) DO NOTHING
RETURNING status;
-- no row returned → SELECT command, target, request_hash, status, result … FOR UPDATE, then:
--   any of command/target/request_hash differs → IDEMPOTENCY_MISMATCH
--   status = 'CLAIMED' → IDEMPOTENCY_IN_PROGRESS
--   status = 'DONE'    → replay result
```

## 说明

- 按 caller 划分命名空间，意味着别的 caller 的键对我来说就是没用过的：我读不到它的结果，也不能接管系统派生的键。
- 一段式命令在一个事务里认领、执行并完成；只有两段式命令会在一次网络调用期间保持 `CLAIMED`。
