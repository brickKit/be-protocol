[English](16-data-lifecycle.md) · [中文](16-data-lifecycle.zh.md)

# P16 Data lifecycle

How every table a component owns is classified, partitioned, sealed, frozen, retained and destroyed: the declaration `migrations/lifecycle.yaml` v1, the engine's guarantees, the read contract for time ranges, and the resource contract `_lifecycle/*`. Schemas: [`lifecycle.schema.json`](../schemas/lifecycle.schema.json), [`data-lifecycle-config.schema.json`](../schemas/data-lifecycle-config.schema.json); tables: `besdk_lifecycle_units`, `besdk_lifecycle_log`, `besdk_holds`, `besdk_erasures`, `besdk_exports` ([ddl/](../ddl/)); REST [`openapi/resource-lifecycle.yaml`](../openapi/resource-lifecycle.yaml); gRPC [`proto/be/lifecycle/v1/lifecycle.proto`](../proto/be/lifecycle/v1/lifecycle.proto).

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P16.1 | MUST | Every component with a database ships `migrations/lifecycle.yaml` v1, embedded with its migrations. Every table its migrations create is declared. Invariants, checked when the declaration is loaded (a violation is fatal and names the table): a `ledger` table has no `pii` column and no `erasure.columns`; a `queue` table declares no `tiers.cold`; a `snapshot` table declares no `retention.min`; every `NUMERIC` column of a table that declares `tiers.cold` has a precision; a table with `tiers.cold` and an erasure action other than `restrict` cannot use a WORM cold store (gate `lifecycle-scan`) | CP-LIFE-04 |
| P16.2 | MUST, INTERNAL | The engine runs as the singleton job `be.lifecycle`. Each step is one transaction with a step lock ([P10.8](10-database.md)) and `lock_timeout`. The runtime role has no DDL ([P10.12](10-database.md)): at run time the engine creates partitions ahead, installs seal guards, drops expired platform and queue partitions (a plain `DETACH` under a short `lock_timeout`) and thaws a cold unit only through the platform's `SECURITY DEFINER` functions: a thaw creates the unit's table detached (`besdk_thaw_create`), loads its rows with plain `INSERT`s, then seals and attaches it (`besdk_thaw_attach`); re-freezing a thawed unit drops it with `besdk_drop_partition`, its cold copy staying. `DETACH PARTITION … CONCURRENTLY` cannot run inside a function or a transaction block, so detaching and dropping frozen business units runs in the migration step, as the owner, on its dedicated connection. The engine keeps guarantees G1–G12 below | — (lifecycle suite) |
| P16.3 | MUST | A read of a time range returns either the complete result or `400` `FAILED_PRECONDITION` with reason `RANGE_COLD` and `metadata` `{online_from, cold_ranges, thaw_allowed, export_allowed}` (`cold_ranges` as `<from>/<to>` pairs, comma-separated). It never truncates silently. A `List` request accepts the optional boolean `include_cold` (default false). A list request without a time range is filtered to the table's `tiers.hot` window (`none` = no window); this is a default filter, not a limit: rows older than the window that are still online (warm) are returned when the request names a range that covers them | CP-LIFE-02 |
| P16.4 | MUST | The resource contract `/{domain}/{name}/_lifecycle/*` and gRPC `be.lifecycle.v1.Lifecycle` are mounted in full; an endpoint not implemented yet answers `501` `CAPABILITY_UNAVAILABLE` with `metadata.capability` | CP-LIFE-03 |
| P16.5 | MUST | A sealed unit is immutable: `UPDATE`, `DELETE` and `TRUNCATE` are refused by triggers calling the platform function `besdk_sealed_guard()` ([ddl/](../ddl/)), which raises SQLSTATE `BE001`; the runtime maps it to `FAILED_PRECONDITION` / `UNIT_SEALED`. `besdk_lifecycle_log` carries the same guard from creation | — |
| P16.6 | MUST | A database migrated on any day accepts writes that day: the platform migration creates the current partition window ([P11.3](11-migrations-and-data-shapes.md)); at run time the window always covers `ahead` | CP-LIFE-01 |
| P16.7 | MUST | Every engine action appends a row to `besdk_lifecycle_log` (append-only, kept forever) and publishes `<domain>.<name>.lifecycle.<action>.v1` through the outbox, `<action>` one of `sealed`, `frozen`, `thawed`, `destroyed`, `erasure_completed` | — |
| P16.8 | MUST | Three permission keys per component guard the resource contract, registered by the project's tooling: `<domain>.<name>.lifecycle.read` (units, exports), `<domain>.<name>.lifecycle.thaw`, `<domain>.<name>.lifecycle.admin` (holds, erasures, destruction approval) | CP-LIFE-03 |
| P16.9 | MUST | `DATA_LIFECYCLE` selects the mode (`on`, `dry-run`, `off`) and the adapters; an adapter the runtime does not have fails the start naming it ([P1.8](01-process-and-lifecycle.md)). A per-table override may only lengthen `retention.min`; an override below the declared minimum fails the start. A YAML value is read with the YAML 1.2 core schema, where `on` and `off` are strings; writers quote them (`mode: "on"`) because YAML 1.1 parsers read them as booleans | — |

## Table classes

| Class | What | Partitioned | Sealed | Cold | Expiry |
|---|---|---|---|---|---|
| `master` | mutable master data, bounded | no | no | no | kept; personal columns anonymised on erasure |
| `reference` | configuration, dictionaries, templates | no | no | no | kept; no personal data |
| `document` | business documents with a state machine | by creation time (recommended) or row units | N months after closed | optional | by retention |
| `ledger` | append-only books | by time or period | `immediate` or `on_signal` | optional, after a checkpoint | legal minimum, then review |
| `audit` | who did what when | by time | `immediate` | optional | ≥ 6 months, default 3 years |
| `queue` | work items with open states | by time | no | never | dropped once no open rows remain |
| `snapshot` | local copies, rebuildable | any | no | never | any time |
| `platform` | runtime-owned (`besdk_*`) | runtime | — | never | runtime (outbox 14 days, cursor and idempotency 30 days) |

## Unit states

`ACTIVE` → `SEALED` → `EXPORTING` → `EXPORTED` → `VERIFIED` → `COLD_PENDING_DROP` → `COLD` → `DESTROYED`; `BLOCKED` when a seal check fails; `THAWED` while a cold unit is re-attached read-only. The state of each unit is in `besdk_lifecycle_units.state`; after a crash the engine resumes from it.

## Guarantees

| # | Guarantee |
|---|---|
| G1 | a migration run on any date accepts writes that day; the window always covers `ahead` |
| G2 | one executor per step per schema at a time; different schemas never block each other; DDL never queues on the hot path |
| G3 | no row is deleted before its declared `retention.min` |
| G4 | data of class `document`, `ledger` or `audit` leaves the database only after a verified cold copy exists; with cold store `none` freezing is skipped and the data stays warm |
| G5 | sealed units are immutable (`UNIT_SEALED`) |
| G6 | the digest chain of sealed units can be verified at any time (`GET _lifecycle/verify`) |
| G7 | a time-range read is complete or answers `RANGE_COLD` |
| G8 | cold reads apply the same data-scope predicate as hot reads; an adapter that cannot express a predicate refuses rather than widens |
| G9 | data under a hold is never destroyed or erased; freezing it is still allowed (the data is kept) |
| G10 | an erasure applies to every tier and leaves a receipt; it is replayed after a point-in-time restore |
| G11 | every action is logged in `besdk_lifecycle_log` and announced by event |
| G12 | every official SDK's planner gives an identical action sequence, item for item, for the same inputs (vectors `lifecycle`) |

## Canonical unit digest

Each row is encoded column by column in declared order, every value in PostgreSQL's text output format, NULL as `\N`; fields separated by `0x1F`, rows by `0x1E`, rows ordered by primary key; the unit digest is SHA-256 of the whole. The chain is `chain_n = SHA-256(chain_{n-1} ‖ unit_digest_n)`. Export, verification and thaw compute it the same way, so any tool can check it independently.

## Notes

- Cold store and cold query adapters are SDK adapters chosen by `DATA_LIFECYCLE`; with both `none` (the 1.0 default) the engine keeps hot and warm tiers only, and `RANGE_COLD` is never answered because nothing is frozen.
- A legal minimum retention is a floor the deployment can only raise.
