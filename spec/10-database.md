[English](10-database.md) · [中文](10-database.zh.md)

# P10 Database: identity, transactions, pools

What every database access of a component does on the wire to PostgreSQL: which role and schema, the statements that open every transaction, isolation and retries, how SQLSTATEs leave a transaction, pool limits, the start-up probe, advisory locks and atomic claims. The engine is PostgreSQL ≥ 14 for a standalone component; a shell requires PostgreSQL ≥ 16 for its NOINHERIT grants ([P19.5](19-shells.md)).

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P10.1 | MUST | The database identity comes only from configuration, as two separate roles and one schema: the **owner** `PG_OWNER_USER` owns the component's tables and runs its DDL (migrations only); the **runtime role** `PG_USER` has DML only, is not a member of the owner role, and is the role every runtime transaction switches to; `PG_SCHEMA` is the schema. All three are required, have no default and are never derived from each other or from the component ID. No derived name (`_rw`, `_archive`, `shell_`) and no literal of the component's own schema or role appears in code, migrations or test fixtures. Component code never issues `SET ROLE` or `SET LOCAL ROLE` itself: only the runtime's store does (gate `identity-literal-scan`) | CP-DB-01 |
| P10.2 | MUST, INTERNAL | Every database access runs inside a transaction that begins with `SET LOCAL ROLE <PG_USER>`, `SET LOCAL search_path TO <PG_SCHEMA>` and `SET LOCAL application_name = '<component ID>'` (the member's ID in a shell): business transactions, the outbox pump, consumers, jobs, the lifecycle engine, projection pulls and the start-up probe, without exception. `search_path` holds the component's schema only. A session-level `SET` is never issued on a pooled connection. The one exception is the dedicated, unpooled migration connection ([P11.1](11-migrations-and-data-shapes.md)): it logs in as the owner, its tool may set a session-level `search_path` and take session-level advisory locks, and it is closed after use. It is the only connection that runs DDL directly. Every statement the runtime sends for a member starts with the comment `/* be:<PG_SCHEMA> */`, so the drivers' per-connection prepared-statement caches (pgx, asyncpg), which are keyed by SQL text, never hand one member a statement prepared for another member's schema on a shared physical connection; a driver whose prepared statements are named instead (node-postgres) keeps statements unnamed or puts the member's schema into the name | CP-DB-01, CP-SHELL-07 |
| P10.3 | MUST | Every transaction sets, with `SET LOCAL`: `statement_timeout = min(5 s, remaining deadline)`, `lock_timeout = 2 s`, `idle_in_transaction_session_timeout = 30 s`; on PostgreSQL ≥ 17 also `transaction_timeout = remaining deadline`. A read snapshot (`REPEATABLE READ READ ONLY`) allows `statement_timeout` up to 30 s. The session `TimeZone` is UTC and is never changed | CP-DB-02 |
| P10.4 | MUST | Isolation defaults to `READ COMMITTED`; a transaction may ask for `REPEATABLE READ` or `SERIALIZABLE`. SQLSTATEs leave a transaction as in [the table below](#sqlstate-mapping): `40001` and `40P01` roll back and re-run the whole transaction body, at most 3 attempts with `10 ms · 2^n` ± jitter, then `ABORTED` / `TX_CONFLICT`; `55P03` → `ABORTED` / `LOCK_TIMEOUT`; `57014` and `25P04` → `DEADLINE_EXCEEDED` / `STATEMENT_TIMEOUT`; `53300` → `UNAVAILABLE` / `DB_TOO_MANY_CONNECTIONS`. Retries are counted in `be_tx_retries_total{reason}` | CP-DB-02 |
| P10.5 | MUST | Pools. Standalone: at most `PG_POOL_MAX` connections. In a shell: one physical pool of `min(Σ members' PG_POOL_MAX, the shell's PG_POOL_MAX)` connections, and per member a limit of its own `PG_POOL_MAX` concurrent connections. A unit of work that cannot get a connection waits at most `min(PG_POOL_ACQUIRE_TIMEOUT, remaining deadline)`, then fails with `RESOURCE_EXHAUSTED` / `DB_POOL_EXHAUSTED`. One member exhausting its budget never affects another. A member's connections are counted in `pg_stat_activity` by `application_name` (P10.2), not by `usename`, which inside a shell is always the shell's login role. Connections are replaced after `PG_CONN_MAX_LIFETIME` and closed after `PG_CONN_MAX_IDLE_TIME` idle | CP-DB-03, CP-SHELL-05 |
| P10.6 | INTERNAL | One unit of work holds at most one connection at a time: opening a transaction while already inside one is refused (a programming error, reason `NESTED_TX`, answered as the generic `INTERNAL`, [P4.3](04-errors.md)). An event handler that writes locally receives the consumer's transaction instead of opening its own | — |
| P10.7 | MUST | Start-up probe, in the background, never part of `/healthz`. **Capabilities**: `server_version_num ≥ 140000` (≥ 160000 in a shell), declarative partitioning, `FOR UPDATE SKIP LOCKED`; a missing capability is fatal and names it ([P1.8](01-process-and-lifecycle.md)). **Identity**, inside a transaction as `PG_USER`: `has_schema_privilege(current_user, current_schema(), 'USAGE')` is true and `… 'CREATE'` is false; `pg_has_role(current_user, <PG_OWNER_USER>, 'MEMBER')` is false; every table in the schema is owned by `PG_OWNER_USER`, and `PG_USER` holds `SELECT, INSERT, UPDATE, DELETE` on each; a failure is logged at ERROR, exported as `be_db_identity_ok = 0`, and makes `/readyz` answer `503`, but does not end the process | CP-DB-01, CP-CORE-05 |
| P10.8 | MUST, INTERNAL | Advisory locks are transaction-level only: `pg_advisory_xact_lock(hashtext(current_schema() \|\| ':' \|\| <name>), hashtext(<parts joined by '\|'>))`, or `pg_try_advisory_xact_lock` with the same key. Two shell members using the same lock name never collide; a component running standalone and in a shell at once, sharing a schema, excludes itself. Session-level advisory locks are never taken on a pooled connection (the migration connection's tool lock is the exception, [P11.1](11-migrations-and-data-shapes.md)) | CP-JOBS-02 |
| P10.9 | MUST | Claims on a queue row or an idempotency key are atomic: `FOR UPDATE SKIP LOCKED`, or `INSERT … ON CONFLICT DO NOTHING` / `DO UPDATE … WHERE … RETURNING`. A plain `SELECT` followed by a write is never used to claim | CP-EVP-03, CP-IDEM-07 |
| P10.10 | MUST (component duty) | A transaction that locks several rows locks them in a fixed order of primary key or business key (for example several stock lines of one reservation by `(warehouse_id, product_id)`) | — (INTERNAL) |
| P10.11 | MUST | Poolers are optional. When used, only in transaction mode. With PgBouncer ≥ 1.21 and `max_prepared_statements > 0` the driver's statement cache may stay on; with any other pooler it is turned off. Migrations connect directly through `PG_MIGRATION_HOST` / `PG_MIGRATION_PORT` | — |
| P10.12 | MUST, partly INTERNAL | The running service never logs in as `PG_OWNER_USER`. brickKit gives the migration container exactly the service's environment and secret files, by design (every value a migration reads stays visible in the component's `config/` file), so the service also receives `PG_OWNER_USER` and the path `PG_OWNER_PASSWORD_FILE`; the serving runtime never reads them, and an official SDK reads the owner's file only on the migrate entry point. The DDL the lifecycle engine needs while the service runs (create a partition ahead, install the seal guard, drop an expired platform or queue partition, thaw a cold unit) goes only through the platform's `SECURITY DEFINER` functions ([ddl/10-lifecycle-functions.sql](../ddl/10-lifecycle-functions.sql)), which the owner creates in the platform migration | CP-DB-05 |

## What every transaction sends

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;            -- or the level the transaction asked for
SET LOCAL ROLE <PG_USER>;                        -- in a shell: the member's own PG_USER
SET LOCAL search_path TO <PG_SCHEMA>;
SET LOCAL application_name = '<component ID>';  -- in a shell: the member's ID
SET LOCAL statement_timeout = '<min(5s, remaining)>';
SET LOCAL lock_timeout = '2s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
SET LOCAL transaction_timeout = '<remaining>';   -- PostgreSQL 17 or later only
/* be:<PG_SCHEMA> */ SELECT …                    -- the body; every statement carries the member's prefix
COMMIT;
```

Role and schema names are quoted as SQL identifiers. `ALTER ROLE … SET` on the login role is a backstop for sessions that bypass the runtime (psql, scripts); it is not the mechanism, because after `SET ROLE` the target role's settings do not apply.

## SQLSTATE mapping

| SQLSTATE | Meaning | Runtime action | Surfaced as (code / reason) |
|---|---|---|---|
| `40001` | serialization failure | retry the body, at most 3 attempts | after the last: `ABORTED` / `TX_CONFLICT` |
| `40P01` | deadlock | same | same |
| `55P03` | lock not available | no retry | `ABORTED` / `LOCK_TIMEOUT` |
| `57014` | statement cancelled | no retry | `DEADLINE_EXCEEDED` / `STATEMENT_TIMEOUT` |
| `25P04` | transaction timeout (17+) | no retry | `DEADLINE_EXCEEDED` / `STATEMENT_TIMEOUT` |
| `25P03` | idle in transaction too long | connection closed by the server | `INTERNAL` (a component bug) |
| `53300` | too many connections | no retry | `UNAVAILABLE` / `DB_TOO_MANY_CONNECTIONS` |
| `23505` | unique violation | no retry | the component maps it to its own reason, usually `ALREADY_EXISTS` |
| `BE001` | raised by the trigger function `besdk_sealed_guard`: a write to a sealed unit ([P16.5](16-data-lifecycle.md)) | no retry | `FAILED_PRECONDITION` / `UNIT_SEALED` |

## Roles

| Role | Login | Owns | Used by |
|---|---|---|---|
| `PG_OWNER_USER` | yes | the tables, sequences and functions in `PG_SCHEMA`, because migrations and the platform migration run as this role | the migration step only |
| `PG_USER` | yes | nothing; `USAGE` on `PG_SCHEMA` and DML on its tables through default privileges; not a member of the owner | the running service (standalone: its login role) |
| shell login role | yes | nothing | a shell; granted every hosted member's `PG_USER` (never an owner) with `INHERIT FALSE, SET TRUE` ([P19.5](19-shells.md)) |

Roles, grants, the default privileges (`ALTER DEFAULT PRIVILEGES FOR ROLE <owner> IN SCHEMA <schema> GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES` and `USAGE, SELECT ON SEQUENCES` to the runtime role) and the backstop role settings are created by the project's database initialisation, never by a migration ([P11.2](11-migrations-and-data-shapes.md)).

## Notes

- Without `LOCAL`, a setting outlives the transaction and the next borrower of the pooled connection runs in another schema, with no error.
- Per-transaction timeouts are the guarantee because a shell logs in as its own role, so a member role's `ALTER ROLE … SET` never applies inside a shell.
