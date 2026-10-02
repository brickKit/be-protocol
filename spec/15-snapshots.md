[English](15-snapshots.md) · [中文](15-snapshots.zh.md)

# P15 Snapshots: local copies of other components' data

A snapshot is a table in the reader's own schema holding another component's data, kept by events, read-through and backfill. It is never a source of truth. Table for backfill progress: `besdk_snapshot_sync` ([ddl/](../ddl/)).

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P15.1 | MUST | A snapshot row carries the upstream aggregate version. Events, read-through and backfill write through one upsert guarded by `WHERE local.version < incoming.version`; an equal version changes nothing | CP-EVS-03 |
| P15.2 | MUST | An event with partial state updates an existing row only, never inserts one. Rows are created only from full state: a full event, `BatchGet` or `List` | CP-EVS-02 |
| P15.3 | MUST | Read-through where possible: a missing row, or one older than the snapshot's `StaleAfter`, is fetched with `BatchGet`, written back, then returned. Backfill at start only for a hub's hot path or a view that needs the full set: page through the upstream `List`, record progress in `besdk_snapshot_sync` so it resumes, and subscribe before backfilling. When the upstream is absent the missing IDs are reported to the caller: a security-relevant use (a credit limit) fails closed, a display use (a name) degrades | — |
| P15.4 | MUST (component duty) | A snapshot nobody reads is removed | — |
| P15.5 | MUST | A snapshot table is declared `class: snapshot` in `lifecycle.yaml` ([P16](16-data-lifecycle.md)) and its upstream is a declared dependency in `component.yaml` (optional or required) | CP-LIFE-04 |

## Upsert

```sql
INSERT INTO <snapshot table> (id, version, …) VALUES ($1, $2, …)
ON CONFLICT (id) DO UPDATE SET version = EXCLUDED.version, …
 WHERE <snapshot table>.version < EXCLUDED.version;
```

For a partial event the statement is an `UPDATE … WHERE id = $1 AND version < $2` instead.

## Notes

- A snapshot and the event cursor ([P12.6](12-events.md)) guard the same thing at two levels: the cursor skips an older event; the version guard keeps an older read-through result from overwriting a newer event.
- A value that must be current (available stock right after confirming) is asked of its owner synchronously, never read from a snapshot.
