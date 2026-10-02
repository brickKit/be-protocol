[English](02-configuration.md) · [中文](02-configuration.zh.md)

# P2 Configuration

Where a component's configuration comes from, how values are typed and parsed, and the keys this protocol defines. The machine-readable catalogue is [`schemas/config-keys.yaml`](../schemas/config-keys.yaml); the gate `protocol-config-scan` checks each component's `configSchema` against it.

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P2.1 | MUST | Configuration comes **only** from the platform: standalone, from the process environment; in a shell, from the member's own entry of `BRICKKIT_SERVED_MEMBERS_CONFIG` ([P19](19-shells.md)). A key is an environment variable name, exactly as brickKit's environment contract defines | — |
| P2.2 | MUST, partly INTERNAL | A component reads only keys declared in its `configSchema`, plus the platform's reserved names (`COMPONENT_ID`, `COMPONENT_VERSION`, `PORT`, `<DEP>_ENDPOINT`, `<DEP>_<PORT>_ENDPOINT`). Official SDKs read the image's `component.yaml` at start and refuse a read of an undeclared key as a programming error (exit 78). Component code never reads the process environment itself (INTERNAL) | CP-CORE-02 |
| P2.3 | MUST | Values are strictly typed by the format the catalogue gives each key: `int`, `bool` (`true` / `false`), `duration` (Go syntax), `url`, `json` (an object), `durations` (comma-separated durations), `enum`, `string`. A value that is present but does not parse is a configuration error ([P1.2](01-process-and-lifecycle.md), exit 78); it never falls back to the default. An empty string for a key with a default means the default. All errors are reported together, one log line each | CP-CORE-02 |
| P2.4 | MUST | No configuration key uses a reserved name or ends in `_ENDPOINT` (brickKit's rule: the platform's value would win silently) | — (gate) |
| P2.5 | MUST | When an optional dependency is not installed, its `*_ENDPOINT` variables **do not exist** (they are not empty). The component degrades as its contract says and does not crash | — |
| P2.6 | MUST | A dependency address is read by stripping the `http://` scheme and a trailing `/` from the injected value. gRPC always uses the port-named variable `<DEP>_GRPC_ENDPOINT`; dialling `<DEP>_ENDPOINT` reaches the HTTP port. A slot family has no such variables: it is reached through its shared `*_URL` key (P2.10) | — |
| P2.7 | MUST | A key declared `secret: true` is injected only through `${VAR}` or `file://` in project configuration. Its value never appears in a log line, an error body, `/_be/info` or a metric label | CP-OBS-04 |
| P2.8 | MUST | A component declares in its `configSchema` every protocol key that the profiles it uses require, with the catalogue's `type`, `secret` flag and default. `AUTHZ_BUNDLE_URL` is not a protocol key and is not declared | — (gate `protocol-config-scan`) |
| P2.9 | MUST | A `secret: true` value whose text is `@file:<absolute path>` is read from that file when it is used, and re-read when the file's modification time changes. This is a runtime file reference, distinct from brickKit's `file://`, which is inlined when deployment files are generated | — |
| P2.10 | MUST | Slot-family addresses. The installed member of a slot family is reached only through the family's shared key (`AUTHZ_URL` for the authorization family, `IAM_URL` for the identity family), never through a dependency edge, so no `*_ENDPOINT` variable exists for it. The value is `http://<member service name>:<member HTTP port>`, with an explicit port and no path (a trailing `/` is stripped); REST paths are appended to it (`{AUTHZ_URL}/authz/v2/bundle`). The family's gRPC target is derived, never configured: the URL's host and the URL's port **+ 1000** (`http://infra-authz-3-0-0:8223` → `infra-authz-3-0-0:9223`), so every member of a family registers its `grpc` extra port as its main port + 1000 (checked by the family's conformance suite). A value without an explicit port, with a path, or whose port + 1000 exceeds 65535 is a configuration error (exit 78) | — (vectors `config`) |
| P2.11 | MUST | Family keys: a few shared keys are read only by the members of a slot family and are never declared by any other component; the catalogue marks them with `applies_when` instead of a profile. In 1.0 there is one: `BOOTSTRAP_ADMIN_LOGIN`, the IdP login name or e-mail address of the first administrator. The identity member binds it to a platform `sub` once, at that person's first login, and says so in its user event (`bootstrap_admin: true`); the authorization member grants its bootstrap administrator role on that event (contract-infra-iam `TOKENS.md`, contract-infra-authz `README.md`). A platform `sub` cannot be configured in advance because it does not exist before the first login | — (gate `protocol-config-scan`) |

## Protocol keys

`Profile` says which components declare the key. Defaults are injected as written in the catalogue. `PG_POOL_MAX` has a different default in a shell's own configuration (40).

| Key | Profile | Required | Default | Format | Meaning |
|---|---|---|---|---|---|
| `PG_HOST` | db | yes | — | string | shared database host |
| `PG_PORT` | db | no | `5432` | int | shared database port |
| `PG_DATABASE` | db | yes | — | string | shared database name |
| `PG_USER` | db | yes | — | string | the runtime role (DML only): the service's login role, and the role every runtime transaction switches to with `SET LOCAL ROLE` ([P10.1](10-database.md)) |
| `PG_PASSWORD` | db | yes | — | string, secret | `PG_USER`'s password, read for every new connection |
| `PG_OWNER_USER` | db | yes | — | string | the owner role: owns the tables, runs migrations; never used by the running service ([P10.12](10-database.md)) |
| `PG_OWNER_PASSWORD` | db | yes | — | string, secret | the owner's password, used by the migration step only |
| `PG_SCHEMA` | db | yes | **none** | string | the component's schema; never derived from the role, never defaulted in code |
| `PG_POOL_MAX` | db | no | `10` | int | standalone: the pool's maximum; in a shell: this member's concurrency budget inside the shared pool ([P10.5](10-database.md)) |
| `PG_POOL_MIN_IDLE` | db | no | `2` | int | idle connections kept open |
| `PG_POOL_ACQUIRE_TIMEOUT` | db | no | `5s` | duration | longest wait for a connection, capped by the remaining deadline |
| `PG_CONN_MAX_LIFETIME` | db | no | `30m` | duration | a connection is replaced after this long |
| `PG_CONN_MAX_IDLE_TIME` | db | no | `5m` | duration | an idle connection is closed after this long |
| `PG_MIGRATION_HOST` | db | no | `PG_HOST` | string | migrations connect here; set when `PG_HOST` is a transaction-mode pooler |
| `PG_MIGRATION_PORT` | db | no | `PG_PORT` | int | as above |
| `EVENT_BUS_URL` | events-pub, events-sub | one of the two | falls back to `NATS_URL` | url | the scheme picks the bus adapter: `nats://`, `postgres://…?schema=be_bus`; `kafka://` reserved ([P12.12](12-events.md)) |
| `NATS_URL` | events-pub, events-sub | one of the two | — | url | shared NATS address |
| `EVENTS_MAX_DELIVER` | events-sub | no | `8` | int | deliveries before a message is dead-lettered, counted by the runtime from the broker's delivery count ([P12.7](12-events.md)); overrides a subscription's own value |
| `EVENTS_BACKOFF` | events-sub | no | `1s,10s,1m,5m,15m,30m,1h` | durations | the runtime's redelivery delays, applied as a negative acknowledgement with that delay; the broker has no backoff of its own ([P12.5](12-events.md)); overrides a subscription's own value |
| `AUTHZ_URL` | auth | yes | — | url | base URL of the installed authorization provider member, by the member's own service name; its gRPC target follows P2.10 |
| `IAM_URL` | — (callers of `infra.iam.v1.IamProvider`; identity members) | no | — | url | base URL of the installed identity member, by the member's own service name; its gRPC target follows P2.10. `IAM_JWKS_URL` is `{IAM_URL}/.well-known/jwks.json` |
| `IAM_JWKS_URL` | auth | yes | — | url | the identity provider's JWKS |
| `IAM_ISSUER` | auth | yes | — | string | the expected `iss`: a stable name of the deployment's platform issuer, recommended `urn:be:<TENANT_ID>:iam`; not an address, unchanged when the identity member is swapped |
| `TENANT_ID` | auth | yes | — | string | the expected `aud` (one deployment is one tenant) |
| `BOOTSTRAP_ADMIN_LOGIN` | — (authorization and identity members only, P2.11) | no | — | string | the IdP login name or e-mail address of the first administrator |
| `BUSINESS_TIMEZONE` | jobs | no | `Asia/Shanghai` | string (IANA zone) | the deployment's default zone; cron schedules evaluate in it. A legal entity's own zone comes from mdm/org ([P11.9](11-migrations-and-data-shapes.md)) |
| `DATA_LIFECYCLE` | lifecycle | no | `{"mode":"on"}` (every adapter `none`) | json or YAML mapping | the lifecycle engine's mode and adapters ([P16](16-data-lifecycle.md), [schema](../schemas/data-lifecycle-config.schema.json)) |
| `JOBS_OVERRIDES` | jobs | no | empty | json | per-job overrides of `interval`, `cron`, `enabled` ([P14](14-background-jobs.md), [schema](../schemas/jobs-overrides.schema.json)) |
| `S3_URL` | blob | yes | — | url | object storage endpoint |
| `S3_PUBLIC_URL` | blob | no | `S3_URL` | url | the address browsers use; presigned URLs are signed for it ([P17.2](17-object-storage.md)) |
| `S3_REGION` | blob | no | `us-east-1` | string | the signing region |
| `S3_FORCE_PATH_STYLE` | blob | no | `false` | bool | path-style addressing |
| `S3_BUCKET` | blob | yes | — | string | the component's own bucket |
| `S3_ACCESS_KEY_ID` | blob | yes | — | string, secret | the component's own credential |
| `S3_SECRET_ACCESS_KEY` | blob | yes | — | string, secret | as above |
| `OTEL_BASE_URL` | all | no | empty (no export) | url | OTLP/HTTP base address; the runtime appends `/v1/traces` (and `/v1/metrics` when exporting metrics) |
| `DEFAULT_LOCALE` | all | no | `zh-CN` | string (BCP 47) | the deployment's default language: the language of a problem body's `title` and `detail` ([P4.1](04-errors.md)); one value per deployment, shared |
| `LOG_LEVEL` | all | no | `info` | enum `debug`, `info`, `warn`, `error` | minimum level written |
| `HTTP_DEFAULT_TIMEOUT` | all with HTTP routes | no | `10s` | duration | default route deadline ([P3.4](03-http-surface.md)) |
| `GRPC_MAX_CONNECTION_AGE` | grpc | no | `5m` | duration | server connection age ([P7.5](07-system-rpc.md)) |
| `SHUTDOWN_GRACE` | all | no | `20s` | duration | in-flight work allowed after `SIGTERM`; keep it below the platform's stop grace period |

Component-defined keys that follow a protocol pattern:

| Pattern | Format | Meaning |
|---|---|---|
| `<SERIES>_NO_FORMAT` | string | the format of a document-number series ([P11.10](11-migrations-and-data-shapes.md)), for example `ORDER_NO_FORMAT` |

Reserved names a component never declares: `COMPONENT_ID`, `COMPONENT_VERSION`, `PORT`, every `*_ENDPOINT`, `BRICKKIT_SERVED_MEMBERS`, `BRICKKIT_SERVED_MEMBERS_CONFIG`.

## Notes

- Protocol keys are also the suite's testability interface: it shortens timers through the same keys an operator would tune (`EVENTS_BACKOFF`, `EVENTS_MAX_DELIVER`, `GRPC_MAX_CONNECTION_AGE`, `JOBS_OVERRIDES`); there is no "test mode" switch.
- `DATA_LIFECYCLE` carries a structured value on purpose: flattened, it would be dozens of keys and could not express per-table overrides. In 1.0 a component-level value replaces the shared value as a whole (brickKit's `$var:` is always a whole value); merging the two is not defined.
- Legal-entity calendars are not configuration: they come from mdm/org.
