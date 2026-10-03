[English](14-background-jobs.md) · [中文](14-background-jobs.zh.md)

# P14 Background jobs

Every piece of work not triggered by a request is one of five declared kinds, supervised by the runtime, with its state in the component's own schema. Tables: `besdk_job_lease`, `besdk_job_slot`, `besdk_job_queue`, `besdk_reconcile` ([ddl/](../ddl/)).

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P14.1 | MUST, INTERNAL | All work not triggered by a request is declared as one of the five kinds below. Module code never runs its own ticker loop (gate `module-ticker-scan`). A job has a name unique within the component; runtime-owned jobs are named with the prefix `be.` (`be.outbox`, `be.lifecycle`, `be.cleanup`, `be.authz.changes`, `be.snapshot.<name>`) | — |
| P14.2 | MUST | Supervision as in [P1.7](01-process-and-lifecycle.md). Every run has a timeout, declared and required; at the timeout the run is cancelled. Two replicas run one cron slot once; a singleton has one holder at a time and another replica takes over within the lease TTL after the holder dies; a queued job runs once across replicas; a job enqueued in a rolled-back transaction does not exist; a failed run is restarted without ending the process | CP-JOBS-01, CP-JOBS-02, CP-JOBS-03, CP-JOBS-04, CP-JOBS-05 |
| P14.3 | MUST | Metrics (every series also carries `component`): `be_job_runs_total{job,result}`, `be_job_duration_seconds{job}`, `be_job_last_success_timestamp_seconds{job}`, `be_queue_depth{kind,state}`, `be_queue_oldest_age_seconds{kind}`, `be_reconcile_pending{name}`, `be_reconcile_oldest_age_seconds{name}`, `be_reconcile_giveups_total{name}` | CP-OBS-03 |
| P14.4 | SHOULD | Read-only operations endpoint `GET /{domain}/{name}/_ops/jobs`, guarded by the key `<domain>.<name>.ops`: each job's kind, last success, last error, and queue depth ([`openapi/ops.yaml`](../openapi/ops.yaml)) | — |
| P14.5 | MUST | `JOBS_OVERRIDES` ([schema](../schemas/jobs-overrides.schema.json)) overrides, per job name, `interval`, `cron` and `enabled`, runtime-owned jobs included. An override naming an unknown job is logged at WARN and ignored. `enabled: false` stops the in-process scheduling only; `job run` still runs the job (P14.8) | CP-JOBS-01 |
| P14.6 | MUST | A schedule is either a five-field cron expression, evaluated in `BUSINESS_TIMEZONE` unless the job declares another IANA zone, or `@every <duration>` (Go duration syntax, at least `1s`), whose slots are the multiples of the duration since the Unix epoch, so every replica computes the same slots. Nothing else is accepted (no seconds field, no `@daily`, no `@reboot`); an invalid schedule, declared or overridden through `JOBS_OVERRIDES`, is a configuration error (exit 78). After downtime only the most recent missed slot runs | CP-JOBS-01 |
| P14.7 | MUST | Handlers are idempotent: at-least-once means a run or a queued job may execute twice; it deduplicates by `unique_key` or a business key. The runtime's cleanup singleton deletes `besdk_job_queue` rows in state `done` 7 days after they finished and `besdk_job_slot` rows 30 days after their slot (`dead` rows stay until an operator removes them); with the outbox (14 days after publication), cursor and idempotency rows (30 days) these are the platform's retention defaults ([P16](16-data-lifecycle.md#table-classes)) | — |
| P14.8 | MAY | Run one job once. A runtime MAY offer the entry point `<entrypoint> job run <name>` (same image, same configuration and secret files): it checks the schema version as the serving entry point does ([P1.8](01-process-and-lifecycle.md)), starts no server and no other background work, runs **one** run of the declared job `<name>` through the same tables as the in-process scheduler, and exits. `cron`: claims the most recent slot at or before now in `besdk_job_slot` (a slot already claimed is a no-op); `singleton`: takes the lease in `besdk_job_lease` for the run (a lease held elsewhere is a no-op); `every` and `reconciler`: one pass, claiming items as usual; `queue`: drains the ready rows of that kind once, within the job's timeout. The holder is `<component ID>/job-run:<instance id>`. Exit 0 after a successful run or a no-op (logged with its reason), 1 when the run failed, 64 for an unknown job name ([P1.1](01-process-and-lifecycle.md)), 78 for a configuration error. It runs whatever `JOBS_OVERRIDES` says about `enabled`, so an operator who moves a heavy job to an external trigger sets `enabled: false` for the in-process copy and triggers `job run` from outside: host cron or a systemd timer with `docker compose --project-directory <root> -p <project> -f .brickkit/generated/compose.yaml run --rm --no-deps <service> job run <name>`, or a hand-written Kubernetes CronJob without the `brickkit.io/project` label. Every trigger, and any number of them at once, still runs a slot once. A runtime that offers it lists `job_run` in `/_be/info` `capabilities` ([P20.4](20-self-description-and-versioning.md)) | CP-JOBS-06 |

## The five kinds

| Kind | Semantics | Mechanism | Table |
|---|---|---|---|
| `every` | runs on every replica on its own timer; safe concurrently because the work it picks up is claimed atomically | timer; work rows claimed with `FOR UPDATE SKIP LOCKED` | — |
| `singleton` | at most one run at a time across all replicas and processes | lease with TTL 30 s, renewed every TTL/3; a lost lease cancels the run; `epoch` is the fencing token, +1 on every takeover | `besdk_job_lease` |
| `cron` | each time slot runs exactly once across all replicas | `INSERT … ON CONFLICT DO NOTHING` on `(name, slot_at)`; whoever inserted runs the slot and sets `done_at`; no leader | `besdk_job_slot` |
| `queue` | enqueued in the business transaction, executed at least once after commit | insert in the business transaction (`ON CONFLICT DO NOTHING` with a `unique_key`); workers claim `state = 'ready' AND run_at <= now()` with `SKIP LOCKED`, set `running` and `lease_until`, run the handler **outside any transaction**; failure increments `attempts` and sets `run_at` from the backoff; exhausted attempts set `dead` and call the dead handler in a transaction; a `running` row past `lease_until` is claimable again | `besdk_job_queue` |
| `reconciler` | drives in-flight processes past their deadline | candidates selected by the component's own SQL (non-terminal and past deadline); each claimed with a lease; handler outside any transaction; outcome applied in a short transaction that re-checks the state machine; backoff; past the maximum, give up (suspend and open an exception task) | `besdk_reconcile` |

`holder` in lease and slot rows is `<component ID>/<instance id>`; in a shell the member's ID, so members never share leases, slots or queues.

## Statements

```sql
-- singleton: take or renew the lease (row created first with INSERT … ON CONFLICT DO NOTHING)
UPDATE besdk_job_lease
   SET holder = $me, epoch = CASE WHEN holder = $me THEN epoch ELSE epoch + 1 END,
       expires_at = now() + $ttl
 WHERE name = $name AND (expires_at < now() OR holder = $me)
RETURNING epoch;

-- cron: claim one slot
INSERT INTO besdk_job_slot (name, slot_at, holder) VALUES ($name, $slot, $me)
ON CONFLICT (name, slot_at) DO NOTHING RETURNING 1;

-- reconciler: claim one item
INSERT INTO besdk_reconcile (name, item_id, lease_until) VALUES ($name, $id, now() + $lease)
ON CONFLICT (name, item_id) DO UPDATE SET lease_until = now() + $lease
 WHERE (besdk_reconcile.lease_until IS NULL OR besdk_reconcile.lease_until < now())
   AND besdk_reconcile.next_at <= now()
RETURNING attempts;
```

Reaching a terminal state deletes the item's `besdk_reconcile` row.

## Notes

- A standalone run and a shell run of the same component, side by side, coordinate through the same rows, because the tables are in the component's schema.
- No Kubernetes CronJob, no `pg_cron`, no external scheduler by default: the work stays in the process. A job that needs isolation is first moved out of its shell (its own container and `resources`); only when that is not enough is it triggered from outside through P14.8, and the external trigger coordinates through the same rows.
