[English](18-observability.md) · [中文](18-observability.zh.md)

# P18 Observability

Traces, log lines and metric names every component emits, in any language, so one query works for every component, standalone or in a shell.

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P18.1 | MUST | **Traces.** W3C Trace Context and Baggage. HTTP and gRPC extract inbound and inject outbound (`traceparent`, `tracestate`, `baggage`). An event carries the producing span's `traceparent` in its envelope; the consumer starts a **new trace with a span link** to the producer's span, not a child span. Resource attributes per member: `service.name` = the component ID, `service.version` = the component version, `service.namespace` = the component's domain (the first segment of its ID, `erp`), `service.instance.id` = the container or pod, `deployment.environment.name` = `DEPLOY_ENV` (default `dev`; the OpenTelemetry semantic-convention name since 1.27, formerly `deployment.environment`). An inbound `traceparent` whose sampled flag is 0 is still propagated: its trace ID is kept, the request's spans are created unsampled, neither recorded nor exported, and outbound calls carry the same flag. Export is OTLP/HTTP to `OTEL_BASE_URL`; empty means no export and no error. Every request, event handler and job run has a span with a valid trace ID, also when nothing is exported, so `trace_id` is always present in logs and problem bodies. In a shell each member has its own tracer provider and meter provider; the exporter and the propagator are shared, and only the shell shuts the exporter down, after every member has stopped. Every instrumentation (HTTP server, gRPC server and client, outbound HTTP, consumers) is given the member's tracer and meter providers and the propagator explicitly, never the process globals; the global tracer provider, a fallback only, carries `service.name` = the shell's own ID, so a span with that name reveals an instrumentation that was missed | CP-OBS-01, CP-SHELL-04, CP-SHELL-09, CP-SHELL-10 |
| P18.2 | MUST | **Logs.** stdout only, one JSON object per line, at most **2048 bytes per line including its terminating newline**. A longer line is shortened so that it **stays one valid JSON object**: string values outside the envelope fields are cut, longest first and at a character boundary, each ending in `…[TRUNCATED]`, and the field `truncated: true` is added; the envelope fields `time`, `level`, `msg`, `component_id`, `component_version`, `trace_id`, `span_id`, `request_id` and `truncated` are never cut. Fields in [the table below](#log-fields). `LOG_LEVEL` sets the minimum level per member. Personal-data keys are redacted automatically by the runtime, never by business code, with the semantics of the vectors `redaction`, which are normative: a key is split into words (snake_case, camelCase, `-` and `.` as separators, case-insensitive); it is protected when the words of a protected name appear in it as one contiguous run (a plural `s` on the last word allowed), so `contact_phone`, `phone_number`, `accessToken` match and `telephone`, `tokenizer` do not; the whole value, of any type, becomes the string `[REDACTED]`; values and the envelope fields are never scanned. Protected names: `phone`, `mobile`, `id_card`, `password`, `bank_card`, `email`, `token`, `secret`, `authorization`, `cookie`, `set_cookie`, `api_key` | CP-OBS-02, CP-OBS-04, CP-OBS-05 |
| P18.3 | MUST | **Metrics.** Prometheus text format at `/metrics` on the main port. Every series carries the label `component=<component ID>`, standalone too. HTTP `route` is the route template, never the raw path; status codes are numeric. Protocol metric names start with `be_` (table below); a component's own metrics start with its domain and name (`erp_sales_…`). In a shell, every member's registry is aggregated on the shell's own `/metrics`, each with its `component` label | CP-OBS-03, CP-SHELL-04 |
| P18.4 | MUST | The access-log line of a protected route carries `sub` and `perm`, so a refused request can be traced to a person and a key; a request answered before its guard ran (a `413`, [P3.6](03-http-surface.md), or a `401` for a token that failed verification) carries what is known at that point. A raw token never appears in any log line | CP-OBS-02 |

## Log fields

| Field | When | Content |
|---|---|---|
| `time` | always | RFC 3339 UTC, nanoseconds |
| `level` | always | `debug`, `info`, `warn`, `error` |
| `msg` | always | an event name or one sentence; `http_request` for the access log, `grpc_request` for the gRPC access log |
| `component_id`, `component_version` | always | in a shell, the member's own values |
| `trace_id`, `span_id` | with an active span | required on access-log lines |
| `request_id` | inside a request | — |
| `sub` | after verification | never the token |
| `act` | with a delegation chain | JSON |
| `caller` | on the system plane | `be-caller` |
| `perm` | on a protected route | the key decided |
| `event_id`, `subject`, `delivery` | inside an event handler | — |
| `job` | inside a job | — |
| `error`, `error.code`, `error.reason` | on an error | `error` is the error text; like every value it is not scanned, so code never puts personal data into error text |
| `http.request.method`, `http.route`, `http.response.status_code`, `duration_ms` | access log | OpenTelemetry semantic-convention names |
| `rpc.service`, `rpc.method`, `rpc.grpc.status_code`, `duration_ms` | gRPC log | as above |

Error levels are decided by the runtime from the code ([P4.6](04-errors.md)).

## Metric names

| Name | Type | Labels (besides `component`) |
|---|---|---|
| `be_http_server_requests_total` | counter | `method`, `route`, `status_code` |
| `be_http_server_duration_seconds` | histogram | `method`, `route` |
| `be_http_client_requests_total` | counter | `target`, `method`, `status_code` |
| `be_http_client_duration_seconds` | histogram | `target`, `method` |
| `be_grpc_server_handled_total` | counter | `service`, `method`, `code` |
| `be_grpc_server_duration_seconds` | histogram | `service`, `method` |
| `be_grpc_client_handled_total` | counter | `target`, `method`, `code` |
| `be_grpc_client_duration_seconds` | histogram | `target`, `method` |
| `be_outbound_inflight` | gauge | `target` |
| `be_db_pool_in_use` | gauge | — |
| `be_db_pool_wait_seconds` | histogram | — |
| `be_tx_retries_total` | counter | `sqlstate` |
| `be_db_identity_ok` | gauge | — |
| `be_secret_reload_failures_total` | counter | `key` (the key name, never the value; [P2.9](02-configuration.md)) |
| `be_outbox_pending` | gauge | — |
| `be_outbox_oldest_age_seconds` | gauge | — |
| `be_events_published_total` | counter | `subject` |
| `be_consumer_handled_total` | counter | `subject`, `result` (`applied`, `skipped`, `nak`, `dlq`) |
| `be_consumer_lag_seconds` | gauge | `subject` |
| `be_dlq_messages_total` | counter | `subject` |
| `be_authz_bundle_age_seconds` | gauge | — |
| `be_authz_projection_lag` | gauge | — |
| `be_authz_denied_total` | counter | `reason` |
| `be_cache_hits_total`, `be_cache_misses_total`, `be_cache_evictions_total` | counter | `name` |
| `be_cache_entries` | gauge | `name` |
| `be_job_runs_total` | counter | `job`, `result` |
| `be_job_duration_seconds` | histogram | `job` |
| `be_job_last_success_timestamp_seconds` | gauge | `job` |
| `be_queue_depth` | gauge | `kind`, `state` |
| `be_queue_oldest_age_seconds` | gauge | `kind` |
| `be_reconcile_pending` | gauge | `name` |
| `be_reconcile_oldest_age_seconds` | gauge | `name` |
| `be_reconcile_giveups_total` | counter | `name` |
| `be_lifecycle_blocked` | gauge | `table`, `reason` |

## Notes

- A span link rather than a child span keeps long asynchronous chains from growing one unbounded trace (OpenTelemetry messaging conventions).
- Audit records are not application logs: they are events written in the business transaction, consumed by an audit component.
