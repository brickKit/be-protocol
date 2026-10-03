[English](README.md) · [中文](README.zh.md)

# Fixture: widget

`conformance/widget` is the component every official SDK implements in `examples/widget` and the component conformance suite (`tools/be-acceptance/conformance/component/`) runs against. It is small, but it touches every profile of the protocol, so three SDKs passing the same suite on it is the evidence that they are equivalent. It is also the model an author copies when writing a component in any language. This file is its behaviour: what each SDK's widget must do, observable from outside.

## Files

| File | What |
|---|---|
| `component.yaml` | brickKit manifest: dependencies, `configSchema` (secrets as `mount: file`), ports (8080 `http`, grpc 9090 `grpc`), stop grace period, migration command, health and readiness checks, `events` |
| `assembly.yaml` | protocol keys (`protocol`, `conformance`, `resources`), permissions, data scopes, edge routes |
| `contracts/widget.openapi.yaml` | user plane; each operation's guard in `x-be-permission`, deadlines in `x-be-deadline-seconds` |
| `contracts/conformance/widget/v1/widget.proto` | system plane `conformance.widget.v1.WidgetService` |
| `contracts/events/widget.events.json` | the three published subjects |
| `contracts/errors.yaml` | the widget's reasons |
| `migrations/0001_widget.sql` | the reference schema; normative, because `conformance/fixtures.yaml` observes these tables |
| `migrations/lifecycle.yaml` | one table per lifecycle class |
| `conformance/fixtures.yaml`, `conformance/samples/` | the gold-sample fixtures file and its payloads |
| `broken-variants.yaml` | the deliberately broken builds and the cases each must fail |

Its dependency `conformance/peer` is contract-only: [../peer/](../peer/README.md).

## Tables

| Table | Class | Holds |
|---|---|---|
| `widgets` | document, monthly partitions | the aggregate; status `DRAFT → APPROVING → APPROVED`, or `SUSPENDED` |
| `widget_lines` | follows `widgets` | lines, `created_at` = the widget's |
| `widget_ledger` | ledger, sealed at once | one entry per approval, numbered gap-free |
| `widget_audit` | audit, sealed at once | one row per command, job run and handled event |
| `widget_jobs` | queue, weekly partitions | one row per notification (`PENDING`, `SENT`, `DEAD`) |
| `owner_snapshots` | snapshot | conformance/peer's owners, by upstream version |
| `widget_kinds` | reference | `STD` (10 lines), `BIG` (100 lines), seeded by the migration |
| `widget_owners` | master, personal data | each user's own profile (`display_name`, `phone`, `email`) |

## User plane

All paths are under `/conformance/widget`.

| Route | Guard | Behaviour |
|---|---|---|
| `GET /kinds` | public | the reference rows; works with no token and before the bundle is loaded |
| `PUT /owners/me` | authenticated | upserts the caller's `widget_owners` row; logs `msg=owner_profile_updated` with `display_name`, `phone`, `email` (the last two must come out `[REDACTED]`) |
| `POST /widgets` | `conformance.widget.create` | one-step idempotent create (fingerprint: every body field but `idempotency_key`); `owner_id` = sub, `dept_path` = the token's; number from `WIDGET_NO_FORMAT` (gapped); `document_date` = today in the legal entity's zone; `amount` = `round(quantity × price)`; outbox `conformance.widget.created.v1`; 201 |
| `GET /widgets` | `conformance.widget.view` | canonical scope predicate over owner / org / region plus shares; cursor paging; `sort=price` or `amount` without `price.read` → 400 `SORT_FORBIDDEN`; `region=` outside the caller's values → 403 `OUT_OF_SCOPE`; masked fields are `null` and listed in `_masked`; `_access` per row |
| `GET /widgets/{id}` | `conformance.widget.view` | 404 when invisible; owner display name from the snapshot (read-through `BatchGetOwners`); `X-Data-As-Of` |
| `GET /widgets/{id}/owner` | `conformance.widget.view` | UserHTTP `GET /conformance/peer/owners/{owner_id}`, forwarding `Authorization`, `X-Request-Id`, `traceparent`, `X-Authz-Revision` and no `be-*` header |
| `POST /widgets/{id}/approve` | `conformance.widget.approve`, 15 s | the two-step command below |
| `POST /widgets/{id}/slow?ms=&via=` | `conformance.widget.view`, 2 s | waits `ms` by `sleep`, `db` (`pg_sleep` in a transaction) or `peer` (`GetReservationStatus`); past 2 s → 504 and the downstream work is cancelled |
| `POST /widgets/{id}/attachments` | `conformance.widget.attach` | presigned PUT, at most 5 min and `size_bytes` (≤ 10 MiB); the object key has no file name |
| `GET /widgets/{id}/attachments/{attachment_id}` | `conformance.widget.view` | presigned GET, at most 5 min |

Field keys: setting `price` needs `conformance.widget.price.edit` (403 `FIELD_FORBIDDEN`); reading `price` and `amount` needs `conformance.widget.price.read`. The runtime also mounts the operations endpoints, `_authz/*`, `_shares/*` (sharing optional: 501 when the provider lacks it) and `_lifecycle/*`.

## Approval

1. Authorize on the target (404 invisible, 403 visible but not allowed), claim the key (`CLAIMED`), require `DRAFT` (else 400 `WIDGET_NOT_DRAFT`), set `APPROVING` with `deadline_at = now + WIDGET_APPROVE_TIMEOUT` (30 s), commit. The widget row is locked `FOR UPDATE` in this step (a suite-held lock gives 409 `LOCK_TIMEOUT`).
2. Outside any transaction, call `PeerService/Reserve` (idempotency key `widget-approve:<id>`, `hold_seconds` = `WIDGET_RESERVE_HOLD_SECONDS`), with the outbound deadline `min(3 s, remaining − 50 ms)` and the retry policy of an `IDEMPOTENT` method.
3. Reserved → one transaction: `APPROVED`, `approved_at`, `reservation_id`, version + 1; a `widget_ledger` entry numbered from `WIDGET_LEDGER_NO_FORMAT` (gap-free per legal entity and fiscal period); outbox `conformance.widget.approved.v1`; enqueue `widget.notify` (`kind=approved`, unique key `approved:<id>`); one `widget_audit` row; the key `DONE` with the response. 200.
4. A definite refusal (`QUOTA_EXCEEDED`, `REJECTED`) → back to `DRAFT`, the claim released, the peer's error relayed with its own domain (400 `conformance/peer` / `QUOTA_EXCEEDED`).
5. An unknown outcome (deadline, `UNAVAILABLE` after retries) → 202 with the widget `APPROVING`; the key stays `CLAIMED`, so the same key answers 409 `IDEMPOTENCY_IN_PROGRESS` until the reconciler finishes.

## System plane

`conformance.widget.v1.WidgetService`: `GetWidget` and `BatchGetWidgets` (≤ 100 ids, `BATCH_TOO_LARGE` above) are `NO_SIDE_EFFECTS` system reads without data scopes; `TouchWidget` is `IDEMPOTENT` (namespace `svc:<be-caller>`; increments `touch_count`, one audit row, no event); `GetTouchStatus` answers by key; `ApproveWidget` is user-facing and always answers `UNAUTHENTICATED` over gRPC. Every call without `be-caller` answers `UNAUTHENTICATED` / `MISSING_CALLER`.

## Events

| Subject | Direction | Behaviour |
|---|---|---|
| `conformance.widget.created.v1` | publish | from `POST /widgets` |
| `conformance.widget.approved.v1` | publish | from approval step 3, by the request or the reconciler |
| `conformance.widget.reverted.v1` | publish | from the `reservation.expired` handler |
| `conformance.owner.updated.v1` | consume, `Apply` | snapshot upsert guarded by version; an older or equal version changes nothing |
| `conformance.reservation.expired.v1` | consume, `Apply`, transaction document | the `APPROVED` widget holding that `reservation_id` returns to `DRAFT`, version + 1, and `conformance.widget.reverted.v1` is published in the same transaction (causation = the handled `ce-id`, hop + 1); a widget not `APPROVED` or another reservation: no change |

Durables: `<instance id with / as _>__<subject with every . as __>` (`conformance_widget-go__conformance__owner__updated__v1`). Retries and dead letters follow `EVENTS_MAX_DELIVER` / `EVENTS_BACKOFF`.

## Background work

| Name | Kind | Behaviour |
|---|---|---|
| `widget.daily` | Cron `0 3 * * *` in `BUSINESS_TIMEZONE` | writes one `widget_audit` row `action=daily_summary` with the count of widgets approved on the previous business date; `JOBS_OVERRIDES` can set `cron` or `enabled`; also runnable once with `job run widget.daily` (P14.8), so `/_be/info` lists `job_run` |
| `widget.notify` | Worker (queue), 5 attempts, backoff `1s,5s,30s,2m` | calls `PeerService/Notify` with the job's unique key, marks the `widget_jobs` row `SENT`; when attempts are exhausted `OnDead` marks it `DEAD` |
| `widget.approve` | Reconciler, every 5 s | candidates `APPROVING` with `deadline_at < now`; asks `GetReservationStatus` by key: reserved → step 3; not found → `Reserve` again; rejected → step 4; after 5 attempts gives up: `SUSPENDED`, the key `DONE` with the suspended widget (200 on replay), `widget.notify` `kind=exception` |
| `be.*` | platform | outbox, cleanup, lifecycle, authz changes, snapshot; not declared by the widget |

## Configuration and degraded mode

Protocol keys as in `component.yaml`; the widget's own: `WIDGET_NO_FORMAT` (default `WG{yyyy}{mm}-{seq:05}`), `WIDGET_LEDGER_NO_FORMAT` (`WL-{le}-{yyyy}{mm}-{seq:06}`), `WIDGET_APPROVE_TIMEOUT` (`30s`), `WIDGET_RESERVE_HOLD_SECONDS` (`900`). An invalid format is a configuration error (exit 78, the key named).

`mdm/org` is an **optional** dependency. Installed: legal-entity calendars (zone, fiscal start month, code) come from it through the SDK's snapshot helper. Absent (the suite never installs it): `MDM_ORG_ENDPOINT` does not exist, the widget does not crash, and every legal entity uses `BUSINESS_TIMEZONE`, fiscal start month 1 and its id as `{le}` code. This is the widget's exercise of P2.5.

## What the suite needs to know

`conformance/fixtures.yaml` follows `schemas/fixtures.schema.json`, which now has a field for every fact the cases need. Where each fact lives:

| Case area | Field in `fixtures.yaml` | For the widget |
|---|---|---|
| CP-AUTH-09 | none: guards come from `x-be-permission` in the OpenAPI file | `public`: `GET /kinds`; `authenticated`: `PUT /owners/me` |
| CP-RPC-03 | `user_facing: true` on the operation | `ApproveWidget` |
| CP-DB-02 | `lock` | `SELECT 1 FROM widgets WHERE id = $1 FOR UPDATE`, held while approving |
| CP-OBS-04 | `pii_log` | `PUT /owners/me` logs `phone` and `email` |
| CP-SCOPE-03, -09, -11 | `filters`, `sort` on the list | dimension parameter `region`; sort parameter `sort`, masked values `price`, `amount` |
| CP-EVS-06 | `setup` and `produces` on a consumed subject | approve first (the canned `Reserve` answer uses `rsv-0001`, the sample's reservation), deliver `reservation-expired.json`, expect `conformance.widget.reverted.v1` |
| CP-JOBS-01 | `jobs.cron` | `widget.daily` with the override `{"cron": "@every 2s"}`; count `daily_summary` audit rows |
| CP-JOBS-06 | `jobs.cron` (the first entry) | two `job run widget.daily` at once with `{"widget.daily": {"enabled": false}}`: one `daily_summary` row, both exit 0 |
| CP-EVP-06, CP-EVS-09 | `events.produces`, `events.consumes` | the same subjects as `component.yaml` `events.publishes` / `events.subscribes` |
| reconciler, CP-IDEM-05 | `jobs.reconcilers` | `Reserve` hangs past the 15 s route deadline: 202 `APPROVING`; then `GetReservationStatus` answers reserved: the widget becomes `APPROVED` |
| CP-LIFE-02 | `range` on the list | `created_after`, `created_before`, `include_cold` |
| blob | `blob` | upload `POST /widgets/{id}/attachments` (`$.upload_url`, `$.max_bytes`), download `GET /widgets/{id}/attachments/{attachment_id}` (`$.download_url`) |
| user-plane HTTP dependency | a `dependencies` key `<METHOD> <path>` | `GET /conformance/peer/owners/{owner_id}`: the fake peer serves HTTP as well as gRPC |
| samples | placeholders | `{id}` is the created widget, `{sub:<persona>}` that persona's sub |

## Broken variants

Built with `BROKEN=<name>`; each breaks one rule. See `broken-variants.yaml`: `accept-refresh`, `healthz-db`, `no-ce-id`, `select-claim`, `no-set-role`, `unbounded-pool`, `no-deadline`, `leak-internal`, `readyz-live-db`, `ipv4-only`, `secret-read-once`, `undeclared-event`.

## Decided here

Beyond the outline the protocol design gives for the widget, for review: the Public route `GET /kinds` and the Authenticated route `PUT /owners/me` (one route per guard kind, and the PII log line); the field key `conformance.widget.price.edit`; `GET /widgets/{id}/owner` (UserHTTP); the attachment routes (blob profile); the rpc `GetTouchStatus` (every cross-component write offers one) and the user-facing `ApproveWidget`; the subject `conformance.widget.reverted.v1` and the subscription to `conformance.reservation.expired.v1` (a handler that publishes, and a transaction-document consumer); `mdm/org` as an optional dependency; the reference schema `migrations/0001_widget.sql`; the contract-only dependency `conformance/peer`.
