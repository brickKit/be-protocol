[English](15-snapshots.md) · [中文](15-snapshots.zh.md)

# P15 快照：别人数据的本地副本

快照是读方自己 schema 里的一张表，存着另一个组件的数据，靠事件、读穿透和回填维持。它永远不是真相源。回填进度表：`besdk_snapshot_sync`（[ddl/](../ddl/)）。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P15.1 | MUST | 快照行带上游的聚合版本。事件、读穿透和回填都通过同一个 upsert 写入，条件是 `WHERE local.version < incoming.version`；版本相等就什么都不改 | CP-EVS-03 |
| P15.2 | MUST | 带部分状态的事件只更新已有的行，从不插入行。行只从完整状态创建：完整事件、`BatchGet` 或 `List` | CP-EVS-02 |
| P15.3 | MUST | 能读穿透就读穿透：缺行，或者行比快照的 `StaleAfter` 旧，就用 `BatchGet` 取来，写回，再返回。只有枢纽的热路径、或需要全量的视图，才在启动时回填：翻上游的 `List`，进度记在 `besdk_snapshot_sync` 里以便续跑，并且先订阅、后回填。上游缺席时，把缺失的 ID 报给调用方：安全相关的用途（信用额度）fail closed，展示用途（名字）降级 | — |
| P15.4 | MUST（组件义务） | 没人读的快照要删掉 | — |
| P15.5 | MUST | 快照表在 `lifecycle.yaml` 里声明为 `class: snapshot`（[P16](16-data-lifecycle.zh.md)），它的上游在 `component.yaml` 里是声明过的依赖（可选或必需） | CP-LIFE-04 |

## Upsert

```sql
INSERT INTO <snapshot table> (id, version, …) VALUES ($1, $2, …)
ON CONFLICT (id) DO UPDATE SET version = EXCLUDED.version, …
 WHERE <snapshot table>.version < EXCLUDED.version;
```

部分状态的事件改用 `UPDATE … WHERE id = $1 AND version < $2`。

## 说明

- 快照和事件游标（[P12.6](12-events.zh.md)）在两个层面守同一件事：游标跳过更旧的事件；版本条件防止更旧的读穿透结果覆盖更新的事件。
- 必须是最新的值（刚确认之后的可用库存）要同步问它的所有者，从不从快照里读。
