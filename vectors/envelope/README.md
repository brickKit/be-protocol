[English](README.md) · [中文](README.zh.md)

# Vectors: envelope

Event ids, the CloudEvents headers, causation and hop count, what a consumer does with a message, the state-mode cursor, redelivery and the names of streams, durables and dead-letter subjects (protocol P11.5, P12; foundations 04, 12, 13). SDK API: the outbox pump, the subscription runtime and `IDTime`; the operations below are the pure functions inside them.

## Files

| File | Cases | Operations |
|---|---|---|
| `ids.json` | 20 | `uuid7` |
| `headers.json` | 17 | `envelope` |
| `derive.json` | 12 | `derive`, `enqueue_context` |
| `inbound.json` | 25 | `accept` |
| `cursor.json` | 19 | `cursor_sequence`, `redelivery` |
| `names.json` | 28 | `stream`, `durable` |

## Operations

| Op | Input | Expected |
|---|---|---|
| `uuid7` | `id` | `canonical` (lower case), `unix_ms`, `created_at` (= `IDTime(id)`, RFC 3339 UTC, milliseconds) |
| `envelope` | `producer` (`component_id`, `version`, `events_file`), `row` (an outbox row: `id`, `subject`, `aggregate_type`, `aggregate_id`, `aggregate_version`, `occurred_at`, `traceparent`, optional `tracestate`, `causation_id`, `hop_count`, `payload_json`), optional `contract.transaction_document` | `headers`: the complete header map, sorted by name, including `Nats-Msg-Id` |
| `derive` | `context.kind`: `request`, `event` (with `handled.id`, `handled.hop_count`), `queued_job` (with the job row's `causation_id`, `hop_count`), `cron`, `singleton`, `every`, `reconciler` | `causation_id`, `hop_count` of an event published there |
| `enqueue_context` | `context` as above | `job_causation_id`, `job_hop_count`: what a queue row stores when enqueued there |
| `accept` | `subscription` (`component_id`, `subject`, `aggregate_type`, `transaction_document`), `headers`, `payload_json`, `delivery` | `action: handle` with the decoded `event`, or `action: dlq` with `dlq_subject` and `added_headers` (`be-dlq-consumer`, `be-dlq-delivery`, `be-dlq-reason`) |
| `cursor_sequence` | `start` (the cursor's version or `null`), `versions[]` delivered in order | `applied[]` (versions that ran the handler), `final` |
| `redelivery` | `delivery` (1-based, the broker's delivery count), `max_deliver`, `backoff[]` (durations), `outcome`: `ok`, `error`, `permanent` (ignored when the delivery is above `max_deliver`), `durable`, `stream_seq` | `action`: `ack`, `nak` with `delay`, or `dlq` with `reason` and `dlq_msg_id`; `handled`: whether the handler ran |
| `stream` | `subject` | `stream` (`BE_<FIRST SEGMENT>`), `filter` (`<first>.>`) |
| `durable` | `component_id`, `subject` | `durable`, `dlq_subject` |

## Rules

- **ids**: 36 characters, hex and hyphens, version nibble `7`, variant `10xx`; upper case is accepted and normalised (RFC 9562); braces, `urn:uuid:`, no hyphens, whitespace are `ID_INVALID`. `created_at` of a partitioned row is the id's 48-bit millisecond time.
- **headers**: `ce-specversion` `1.0`; `ce-id` = `Nats-Msg-Id` = the row id; `ce-source` the producing component (in a shell, the member); `ce-type` the subject; `ce-subject` the aggregate id; `ce-time` = `occurred_at` in UTC with `Z`, fractional seconds only when non-zero, trailing zeros removed, at most 6 digits; `content-type: application/json`; `ce-dataschema` = `<component>@<version>/contracts/events/<file>#<subject>`; `ce-aggregatetype`, `ce-aggregateversion` (decimal, ≥ 1); `ce-hopcount` always present; `ce-causationid`, `traceparent` and `tracestate` omitted when empty; `ce-legalentity` = the payload's `legal_entity_id` when it is a non-empty string.
- **payload size**: a payload above 64 KiB (65,536 bytes of `payload_json`, UTF-8) is refused at publish (`PAYLOAD_TOO_LARGE`); exactly 65,536 bytes is published (P12.2).
- **transaction-document events** (`x-transaction-document: true` in the events contract, whose payload then requires `legal_entity_id`): one cannot be published without it (`LEGAL_ENTITY_MISSING`), and a consumer dead-letters one whose header is missing or disagrees with the payload.
- **derive**: from a request or any scheduled job (cron, singleton, every, reconciler): causation empty, hop 0. In a handler: causation = the handled `ce-id`, hop = its hop + 1. A queued job stores, when enqueued, what an event published at that moment would carry, and publishes with exactly those values. Publishing is never refused for its hop count.
- **accept**: dead-letter reasons are `ENVELOPE_INVALID` (missing or malformed required header, wrong `ce-specversion`, `ce-type` other than the subscribed subject, `ce-aggregatetype` other than the contract's, non-JSON `content-type`, integers with a sign or leading zero), `HOP_LIMIT` (hop count above 10), `PAYLOAD_INVALID` (not a JSON object), `LEGAL_ENTITY_MISSING`. Messages with only the old `X-` headers are never read. A subscription that declares no aggregate type takes `ce-aggregatetype` from the message as it is (P12.6); every case here declares one.
- **cursor (state mode)**: a version is applied only when it is greater than the cursor; equal and older versions are skipped; any shuffle with duplicates ends in the same final state.
- **redelivery** (P12.5, P12.7): the broker's durable has `max_deliver` −1 and no backoff; the runtime decides. On receipt, a delivery `d > max_deliver` goes to the dead letters without running the handler (`MAX_DELIVER`); otherwise a failed delivery is nak'ed with `backoff[min(d, len) − 1]`, so the last allowed delivery `d = max_deliver` still naks; a permanent error goes at once (`PERMANENT`). The dead-letter message ID is `dlq:<durable>:<stream sequence>`.
- **names**: subjects have at least four segments (`<domain>.<name>.<event…>.v<n>`, P12.3), each `[a-z][a-z0-9]*(_[a-z0-9]+)*` (starts with a letter; no leading, trailing or double underscore; no hyphen), the last `v<n>` with n ≥ 1. Durable = component id with `/` as `_`, then `__`, then the subject with every `.` as `__` (`erp_finance__sales__order__created__v1`). Because no segment contains `__` or starts or ends with `_`, and a component id contains no `_`, the name splits back uniquely: `crm.lead.stage_changed.v1` and `crm.lead_stage.changed.v1` keep distinct names. Dead-letter subject = `dlq.<durable>.<subject>`.

## Errors

| Class | Where |
|---|---|
| `ID_INVALID` | `uuid7`, `envelope` (the outbox id) |
| `SUBJECT_INVALID`, `COMPONENT_INVALID` | `envelope`, `stream`, `durable` |
| `ENVELOPE_INVALID`, `LEGAL_ENTITY_MISSING` | `envelope` (publishing); the same names appear as `be-dlq-reason` values in `accept` |
| `PAYLOAD_TOO_LARGE` | `envelope` (publishing): the payload is above 64 KiB |

## Decided here

For review: the `ce-time` precision rule; omitting empty `ce-causationid` / `traceparent` headers instead of sending them empty; a queued job's causation is captured at enqueue time; the `be-dlq-reason` vocabulary (`ENVELOPE_INVALID`, `HOP_LIMIT`, `PAYLOAD_INVALID`, `LEGAL_ENTITY_MISSING`, `MAX_DELIVER`, `PERMANENT`); `be-dlq-consumer` carries the durable name. Durable names are injective (`.` becomes `__`, see **names**): `erp.x_y.done.v1` and `erp.x.y_done.v1` keep distinct durables.

## Regenerate

`python3 gen/gen_envelope.py`; cross-check `node gen/xcheck_envelope.mjs .`.
