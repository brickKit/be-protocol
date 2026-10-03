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
| P2.5 | MUST | When an optional dependency is not installed, its `*_ENDPOINT` variables **do not exist** (they are not empty); so do the family address keys of a slot family whose member does not run (P2.10). The component degrades as its contract says and does not crash | — |
| P2.6 | MUST | A dependency address is read by stripping the `http://` scheme and a trailing `/` from the injected value. gRPC always uses the port-named variable `<DEP>_GRPC_ENDPOINT`; dialling `<DEP>_ENDPOINT` reaches the HTTP port. A slot family has no such variables: it is reached through its address keys `*_URL` and `*_GRPC_URL` (P2.10), read the same way | — |
| P2.7 | MUST | A key declared `secret: true` is delivered **as a file**, never as an environment value: it is declared `mount: file` and named `…_FILE` (P2.12), and its variable holds the path of the file brickKit mounts, `/run/brickkit/secrets/<versioned service name>/<KEY>` (a host path for `mode: local` / `debug`; in a shell the member's entry carries the same path, [P19](19-shells.md)). In project configuration its value is written only as `${VAR}`, `file://` or, on Kubernetes, `existingSecret`. The secret value never appears in an environment variable, a log line, an error body, `/_be/info` or a metric label | CP-OBS-04, CP-CORE-14 |
| P2.8 | MUST | A component declares in its `configSchema` every protocol key that the profiles it uses require, with the catalogue's `type`, `secret`, `mount` and default. be-ops generates this block of `configSchema` from the catalogue, by profile, and the gate fails when a component's block differs from what it would generate; only the component's own keys are written by hand. `AUTHZ_BUNDLE_URL` and `IAM_JWKS_URL` are not protocol keys and are not declared | — (gate `protocol-config-scan`) |
| P2.9 | MUST | A secret is read from its file when it is used and re-read when the file changes: the runtime compares the file's modification time and size at most 30 s apart (a file-system watch MAY make it sooner), never restarts for it, and logs one INFO line naming the key per change. A text secret loses exactly one trailing LF or CRLF (vectors `config`, `secret_text`); a component's own binary secret is handed over byte for byte. A new value applies without a restart: a database password to the connections opened after the change (open connections live until `PG_CONN_MAX_LIFETIME`); an object-storage credential pair is re-read as a pair; a signing key rotates with its JWKS overlap (contract-infra-iam `TOKENS.md`). A file that cannot be read after a change keeps the last good value, logs an ERROR naming the key and counts `be_secret_reload_failures_total{key}`; at start an unreadable or empty required secret is a configuration error (exit 78). brickKit's `file://` is unrelated: it fills the file's content at generation time | CP-DB-06 |
| P2.10 | MUST | Slot-family addresses. The installed member of a slot family is reached only through the family's address keys, never through a dependency edge, so no `*_ENDPOINT` variable exists for it: `AUTHZ_URL` and `AUTHZ_GRPC_URL` for the authorization family, `IAM_URL` and `IAM_GRPC_URL` for the identity family. The project writes each once, in `config/vars.yaml`, as a brickKit `$endpoint:` reference to the member (`AUTHZ_URL: $endpoint:infra/authz`, `AUTHZ_GRPC_URL: $endpoint:infra/authz:grpc`), and components take it with `$var:`; swapping the member changes one line per key, and the value follows versions, shells and local runs exactly as `*_ENDPOINT` does. A value is `http://<host>:<port>`, explicit port, no path (a trailing `/` is stripped): REST paths are appended to the `*_URL` value (`{AUTHZ_URL}/authz/v2/bundle`), and the `*_GRPC_URL` value without `http://` is the gRPC dial target. Nothing is derived from anything else: no port arithmetic. When the member does not run, brickKit leaves the key out; an optional key then degrades, a required one stops the start. A value without an explicit port, with a path or with another scheme is a configuration error (exit 78) | — (vectors `config`) |
| P2.11 | MUST | Family keys: a few shared keys are read only by the members of a slot family and are never declared by any other component; the catalogue marks them with `applies_when` instead of a profile. In 1.0 there is one: `BOOTSTRAP_ADMIN_LOGIN`, the IdP login name or e-mail address of the first administrator. The identity member binds it to a platform `sub` once, at that person's first login, and says so in its user event (`bootstrap_admin: true`); the authorization member grants its bootstrap administrator role on that event (contract-infra-iam `TOKENS.md`, contract-infra-authz `README.md`). A platform `sub` cannot be configured in advance because it does not exist before the first login | — (gate `protocol-config-scan`) |
| P2.12 | MUST | Secret declarations. A `configSchema` item is `secret: true` exactly when it is declared `mount: file`, and exactly when its name ends in `_FILE`, for protocol keys and a component's own keys alike (`PG_PASSWORD_FILE`, `S3_SECRET_ACCESS_KEY_FILE`, `APP_TOKEN_SIGNING_KEY_FILE`). No other key ends in `_FILE`. brickKit's own rules hold too: `mount: file` only with `secret: true`, only on a `string` | CP-CORE-14 (gate `protocol-config-scan`, vectors `config`) |

## Protocol keys

`Profile` says which components declare the key. Defaults are injected as written in the catalogue. `PG_POOL_MAX` has a different default in a shell's own configuration (40).

| Key | Profile | Required | Default | Format | Meaning |
|---|---|---|---|---|---|
| `PG_HOST` | db | yes | — | string | shared database host |
| `PG_PORT` | db | no | `5432` | int | shared database port |
| `PG_DATABASE` | db | yes | — | string | shared database name |
| `PG_USER` | db | yes | — | string | the runtime role (DML only): the service's login role, and the role every runtime transaction switches to with `SET LOCAL ROLE` ([P10.1](10-database.md)) |
| `PG_PASSWORD_FILE` | db | yes | — | path, secret file | the file holding `PG_USER`'s password; re-read when it changes, a new value applies to new connections (P2.9) |
| `PG_OWNER_USER` | db | yes | — | string | the owner role: owns the tables, runs migrations; never used by the running service ([P10.12](10-database.md)) |
| `PG_OWNER_PASSWORD_FILE` | db | yes | — | path, secret file | the file holding the owner's password, read by the migration step only |
| `PG_SCHEMA` | db | yes | **none** | string | the component's schema; never derived from the role, never defaulted in code |
| `PG_POOL_MAX` | db | no | `10` | int | standalone: the pool's maximum; in a shell: this member's concurrency budget inside the shared pool ([P10.5](10-database.md)) |
| `PG_POOL_MIN_IDLE` | db | no | `2` | int | idle connections kept open |
| `PG_POOL_ACQUIRE_TIMEOUT` | db | no | `5s` | duration | longest wait for a connection, capped by the remaining deadline |
| `PG_CONN_MAX_LIFETIME` | db | no | `30m` | duration | a connection is replaced after this long |
| `PG_CONN_MAX_IDLE_TIME` | db | no | `5m` | duration | an idle connection is closed after this long |
| `PG_MIGRATION_HOST` | db | no | `PG_HOST` | string | the migration step connects here, directly to PostgreSQL; set when `PG_HOST` is a transaction-mode pooler ([P11.1](11-migrations-and-data-shapes.md)) |
| `PG_MIGRATION_PORT` | db | no | `PG_PORT` | int | the migration step's port |
| `EVENT_BUS_URL` | events-pub, events-sub | one of the two | falls back to `NATS_URL` | url | the scheme picks the bus adapter: `nats://`, `postgres://…?schema=be_bus`; `kafka://` reserved ([P12.12](12-events.md)) |
| `NATS_URL` | events-pub, events-sub | one of the two | — | url | shared NATS address |
| `EVENTS_MAX_DELIVER` | events-sub | no | `8` | int | deliveries before a message is dead-lettered, counted by the runtime from the broker's delivery count ([P12.7](12-events.md)); overrides a subscription's own value |
| `EVENTS_BACKOFF` | events-sub | no | `1s,10s,1m,5m,15m,30m,1h` | durations | the runtime's redelivery delays, applied as a negative acknowledgement with that delay; the broker has no backoff of its own ([P12.5](12-events.md)); overrides a subscription's own value |
| `AUTHZ_URL` | auth | yes | — | url | REST base of the installed authorization member; `$endpoint:<member ID>` in `config/vars.yaml` (P2.10) |
| `AUTHZ_GRPC_URL` | — (callers of `infra.authz.v2.AuthzProvider`: owners of a shareable resource type, callers of `Check` or `ListObjects`, identity members) | yes | — | url | its gRPC address, `$endpoint:<member ID>:grpc`; the dial target is the value without `http://` |
| `IAM_URL` | auth | yes | — | url | REST base of the installed identity member, `$endpoint:<member ID>`; the JWKS is `{IAM_URL}/.well-known/jwks.json` ([P5.4](05-identity.md)) |
| `IAM_GRPC_URL` | — (callers of `infra.iam.v1.IamProvider`) | no | — | url | its gRPC address, `$endpoint:<member ID>:grpc`; absent: the reads degrade as the identity contract says |
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
| `S3_ACCESS_KEY_ID_FILE` | blob | yes | — | path, secret file | the file holding the component's own access key ID; re-read together with the secret key |
| `S3_SECRET_ACCESS_KEY_FILE` | blob | yes | — | path, secret file | the file holding the component's own secret access key |
| `OTEL_BASE_URL` | all | no | empty (no export) | url | OTLP/HTTP base address; the runtime appends `/v1/traces` (and `/v1/metrics` when exporting metrics) |
| `DEFAULT_LOCALE` | all | no | `zh-CN` | string (BCP 47) | the deployment's default language: the language of a problem body's `title` and `detail` ([P4.1](04-errors.md)); one value per deployment, shared |
| `LOG_LEVEL` | all | no | `info` | enum `debug`, `info`, `warn`, `error` | minimum level written |
| `HTTP_DEFAULT_TIMEOUT` | all with HTTP routes | no | `10s` | duration | default route deadline ([P3.4](03-http-surface.md)) |
| `GRPC_MAX_CONNECTION_AGE` | grpc | no | `5m` | duration | server connection age ([P7.5](07-system-rpc.md)) |
| `SHUTDOWN_GRACE` | all | no | `25s` | duration | in-flight work allowed after `SIGTERM`; at least 5 s below `deployment.stopGracePeriodSeconds` ([P1.12](01-process-and-lifecycle.md)) |

Component-defined keys that follow a protocol pattern:

| Pattern | Format | Meaning |
|---|---|---|
| `<SERIES>_NO_FORMAT` | string | the format of a document-number series ([P11.10](11-migrations-and-data-shapes.md)), for example `ORDER_NO_FORMAT` |

Reserved names a component never declares: `COMPONENT_ID`, `COMPONENT_VERSION`, `PORT`, every `*_ENDPOINT`, `BRICKKIT_SERVED_MEMBERS`, `BRICKKIT_SERVED_MEMBERS_CONFIG`. The suffix `_FILE` belongs to file-delivered secrets (P2.12).

Retired names, never declared: `AUTHZ_BUNDLE_URL` (use `AUTHZ_URL`), `IAM_JWKS_URL` (`{IAM_URL}/.well-known/jwks.json`), `PG_PASSWORD`, `PG_OWNER_PASSWORD`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` (each replaced by its `…_FILE` key).

## Notes

- Protocol keys are also the suite's testability interface: it shortens timers through the same keys an operator would tune (`EVENTS_BACKOFF`, `EVENTS_MAX_DELIVER`, `GRPC_MAX_CONNECTION_AGE`, `JOBS_OVERRIDES`); there is no "test mode" switch.
- `DATA_LIFECYCLE` carries a structured value on purpose: flattened, it would be dozens of keys and could not express per-table overrides. In 1.0 a component-level value replaces the shared value as a whole (brickKit's `$var:` is always a whole value); merging the two is not defined.
- Legal-entity calendars are not configuration: they come from mdm/org.
- Secrets are files because an environment variable is visible in `docker inspect` and in a Pod's spec, is carried out by crash dumps and debug output, and is fixed when the process starts; a file can be replaced under a running process. brickKit adds no `_FILE` suffix: the suffix is this protocol's naming rule. On Docker it mounts a read-only directory (not compose `secrets:`, whose single-file mounts never show a replacement), on Kubernetes a projected Secret volume, also for `existingSecret`. Podman and SELinux hosts are untested: a directory mount there may need relabelling.
- Family addresses are explicit keys filled by `$endpoint:` rather than a port rule because a member's real ports come from its own `component.yaml`: a member may put its gRPC port anywhere, and nothing compares hand-written service names with `brickkit.yaml` any more.
