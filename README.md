[English](README.md) · [中文](README.zh.md)

# be-protocol

The BrickEnterprise **component protocol**: everything a component must do, at the wire, table and configuration level, to be a correct member of a BrickEnterprise project, whatever language it is written in. This repository holds the normative text, the machine-readable schemas, the reference DDL of the tables the runtime owns, the semantic vectors and the fixture-component contract. It holds no implementation.

**Protocol version: 1.0. Release: `v1.0.0-rc.2`** (release candidate; frozen as `v1.0.0` after the pilot components pass). It relies on **brickKit ≥ v1.4.0** (`readinessCheck`, `stopGracePeriodSeconds`, port `protocol`, `events`, `mount: file`, `$endpoint:`, `release.checks`).

## Who implements it

| Implementation | Language | Status |
|---|---|---|
| `brickKit/be-sdk-go` | Go | official SDK, implements protocol 1.0 from v0.6.0 |
| `brickKit/be-sdk-python` | Python | official SDK, implements protocol 1.0 from v0.6.0 |
| `brickKit/be-sdk-ts` | TypeScript | official SDK, implements protocol 1.0 from v0.6.0 |
| any other | any | a component in any language joins a project once it passes the conformance suite for the profiles it uses; it runs standalone, and joins a shell only once its language has an official SDK and shell launcher ([P19](spec/19-shells.md)) |

The three official SDKs are reference implementations of this text. **No SDK may have a behaviour this text does not state**; a behaviour is added here first ([Versioning](#versioning)).

## How to read it

- Start with [spec/00-reading-the-spec.md](spec/00-reading-the-spec.md): terms, requirement levels, requirement IDs and case IDs.
- Then the chapter for what you are doing. One file per protocol area, `P1` to `P20`:

| Chapter | File | Covers |
|---|---|---|
| P1 | [01-process-and-lifecycle](spec/01-process-and-lifecycle.md) | entry points, start order, `/healthz`, `/readyz` and the declared checks, shutdown and the stop grace period, listening on IPv4 and IPv6, supervision, exit codes |
| P2 | [02-configuration](spec/02-configuration.md) | where configuration comes from, typing, secrets as files, slot-family addresses through `$endpoint:`, the protocol keys |
| P3 | [03-http-surface](spec/03-http-surface.md) | paths, request id, trace, deadlines, server timeouts, body limit, paging |
| P4 | [04-errors](spec/04-errors.md) | problem+json, gRPC `ErrorInfo`, GraphQL, reason catalogues, log levels |
| P5 | [05-identity](spec/05-identity.md) | JWT verification, JWKS, claims, stale tokens |
| P6 | [06-authorization](spec/06-authorization.md) | bundle, decision chain, levels, subject set, canonical predicate, resource contract, projection |
| P7 | [07-system-rpc](spec/07-system-rpc.md) | gRPC metadata, interceptors, server and client parameters, retries, bulkhead, batch limits |
| P8 | [08-outbound-http](spec/08-outbound-http.md) | user-plane HTTP to other components, third-party HTTP, no network in a transaction |
| P9 | [09-deadlines-and-retries](spec/09-deadlines-and-retries.md) | the budget hop by hop, retry layers (summary) |
| P10 | [10-database](spec/10-database.md) | identity, per-transaction settings, isolation and retries, pools, probes, advisory locks, claims |
| P11 | [11-migrations-and-data-shapes](spec/11-migrations-and-data-shapes.md) | migration rules, platform migration, keys, money, dates, legal entity, numbering |
| P12 | [12-events](spec/12-events.md) | CloudEvents envelope, outbox, streams, durables, cursor, handlers, dead letters, replay, the `events` declaration |
| P13 | [13-idempotency](spec/13-idempotency.md) | caller namespaces, binding, replay, order of checks, retention |
| P14 | [14-background-jobs](spec/14-background-jobs.md) | `every`, `singleton`, `cron`, `queue`, reconcilers, supervision, metrics, running one job once |
| P15 | [15-snapshots](spec/15-snapshots.md) | local copies of other components' data |
| P16 | [16-data-lifecycle](spec/16-data-lifecycle.md) | `lifecycle.yaml`, the engine, `RANGE_COLD`, `_lifecycle/*`, sealed units |
| P17 | [17-object-storage](spec/17-object-storage.md) | S3, one bucket per component, presigned URLs |
| P18 | [18-observability](spec/18-observability.md) | traces, log lines, metric names |
| P19 | [19-shells](spec/19-shells.md) | what a shell launcher and its members must do |
| P20 | [20-self-description-and-versioning](spec/20-self-description-and-versioning.md) | `/_be/info`, the protocol version a component declares, what `component.yaml` declares |

- Every chapter is wire-level only: headers, status codes, JSON fields, table shapes, configuration keys, metric and log field names. Nothing here is one language's API.
- English is canonical; each `X.md` has a Chinese mirror `X.zh.md` with the same `##` sections.

## Repository layout

| Path | Holds | Normative |
|---|---|---|
| `spec/` | the protocol text, P1–P20 | yes |
| `schemas/` | JSON Schemas (2020-12) and YAML catalogues the text references ([index](#schemas)) | yes |
| `ddl/` | reference DDL of the `besdk_*` tables, PostgreSQL ≥ 14 | yes: an SDK's platform migration produces exactly these columns, types, keys and indexes |
| `proto/` | `be/v1/limits.proto` (the `max_items` field option), `be/lifecycle/v1/lifecycle.proto` | yes |
| `openapi/` | the REST fragments every component mounts: `_authz`, `_shares`, `_lifecycle`, operations endpoints | yes |
| `vectors/` | semantic vectors: JSON cases with inputs and the expected output, read by every SDK's unit tests (money, calendar, numbering, fingerprints, envelope derivation, errors, config parsing, redaction). Authorization decision vectors are canonical in the family contract `brickKit/contract-infra-authz` (`vectors/decision/`), not here | yes |
| `fixtures/widget/` | the fixture component `conformance/widget`: its contracts, behaviour and the golden `conformance/fixtures.yaml` | yes |
| `fixtures/peer/` | the widget's contract-only dependency `conformance/peer`, answered by the suite's fake peer (gRPC and HTTP) | yes |
| `fs.go`, `go.mod` | the only code: `//go:embed` exporting the files above as an `fs.FS` for Go consumers | — |
| `Makefile`, `scripts/`, `buf.yaml`, `redocly.yaml`, `third_party/` | the repository's own checks: `make check` runs schema and table validation (`scripts/validate.py`), ID cross-references (`scripts/xref.py`), the DDL test on throwaway PostgreSQL 14 and 16 (`scripts/ddltest.sh`), `buf lint` / `buf build`, Redocly lint, `go vet`, vector freshness, `SHA256SUMS` and the independent vector cross-checks, every step in a container; `third_party/` holds `google/type/date.proto`, which the widget imports | — |

### Schemas

| File | Validates or lists |
|---|---|
| [`config-keys.yaml`](schemas/config-keys.yaml) | catalogue of protocol configuration keys: name, configSchema type, value format, default, secret, profile (validated by `config-keys.schema.json`) |
| [`errors-be.yaml`](schemas/errors-be.yaml) | the reserved reasons of domain `be` (validated by `errors-yaml.schema.json`) |
| [`errors-yaml.schema.json`](schemas/errors-yaml.schema.json) | a component's `contracts/errors.yaml` |
| [`problem.schema.json`](schemas/problem.schema.json) | the REST error body (RFC 9457 with AIP-193 members) |
| [`envelope.schema.json`](schemas/envelope.schema.json) | the CloudEvents headers of an event message |
| [`events-contract.schema.json`](schemas/events-contract.schema.json) | a component's `contracts/events/*.events.json` |
| [`access-token.schema.json`](schemas/access-token.schema.json) | the access-token claims a component requires and reads (P5) |
| [`lifecycle.schema.json`](schemas/lifecycle.schema.json) | `migrations/lifecycle.yaml` v1 |
| [`data-lifecycle-config.schema.json`](schemas/data-lifecycle-config.schema.json) | the value of the `DATA_LIFECYCLE` key |
| [`jobs-overrides.schema.json`](schemas/jobs-overrides.schema.json) | the value of the `JOBS_OVERRIDES` key |
| [`assembly-protocol.schema.json`](schemas/assembly-protocol.schema.json) | the `assembly.yaml` keys this protocol reads: `protocol`, `language`, `conformance`, `resources`, `requires_capabilities` |
| [`info.schema.json`](schemas/info.schema.json) | the `GET /_be/info` response |
| [`fixtures.schema.json`](schemas/fixtures.schema.json) | a component's `conformance/fixtures.yaml` |
| [`conformance-cases.yaml`](schemas/conformance-cases.yaml) | the conformance profiles, when each applies, and every case ID with the requirement it tests |
| [`compconf-report.schema.json`](schemas/compconf-report.schema.json) | the suite's machine-readable report |

## Conformance

The black-box suite is `conformance/component/` of `brickKit/be-acceptance` (in an assembly project: `tools/be-acceptance/conformance/component/`; informal name *compconf*). It runs against a **running container**, never reads source, and so judges every language the same way. Profiles are selected automatically from the component's manifests:

| Profile | Applies when |
|---|---|
| `core` | always |
| `obs` | always |
| `err` | always |
| `auth` | the component has any route that is not Public; an OpenAPI operation without `x-be-permission` counts as not Public (fail closed, [P3.16](spec/03-http-surface.md)) |
| `scope` | `data_scopes` is not `none`, or `resources` is declared |
| `grpc` | an extra port is named `grpc` |
| `outbound` | `dependencies.components` is not empty |
| `events-pub` | `component.yaml` `events.publishes` is not empty (the subjects of its event contract) |
| `events-sub` | `component.yaml` `events.subscribes` is not empty (the subjects of its fixtures' `events.consumes`) |
| `idempotency` | any write accepts `idempotency_key` or `Idempotency-Key` |
| `db` | `configSchema` declares `PG_SCHEMA` or `PG_HOST` (the trigger key, [P2.8](spec/02-configuration.md)) |
| `jobs` | the component has a database (platform jobs always exist) |
| `lifecycle` | the component has a database |
| `blob` | `configSchema` declares `S3_BUCKET` or `S3_URL` |
| `shell` | `component.yaml` has `shell.members` |

A MUST case that fails fails the run; a SHOULD case that fails is a warning. Only optional cases may be skipped, each with a reason, in `assembly.yaml` under `conformance.skip`. A case whose `applies_when` the component does not meet (CP-ERR-02 without a `grpc` port, CP-ERR-03 without a database) is reported as not applicable: neither skipped nor failed. The case list is [`schemas/conformance-cases.yaml`](schemas/conformance-cases.yaml).

The suite runs when a component is released: `component.yaml` declares `release: {checks: [[make, conformance]]}` ([P20.5](spec/20-self-description-and-versioning.md)), and brickKit (≥ v1.4.0) refuses to tag or publish a version whose suite fails. A project keeps a suite report only for a component or shell that does not declare that check (gate `compconf-record-scan`).

Rules a black box cannot observe are marked **INTERNAL**: official SDKs keep them with their own tests; a component in another language states in its `AGENTS.md` how it keeps each one, and review checks it.

## Versioning

- **Protocol version** `MAJOR.MINOR` (here `1.0`) is what a component declares (`protocol: "1.0"` in `assembly.yaml`) and reports in `/_be/info`. The suite keeps one case set per minor; a component is always tested against the version it declares.
- **Release tags** are semver with a `v` (`v1.0.0`), because Go modules import this repository.
  - **patch**: wording, clarifications, more vectors; no semantic change.
  - **minor**: only optional surface: a new capability bit, a new optional endpoint, field, header, key or reason. The meaning of what 1.0 defines never changes.
  - **major**: anything that would make a conforming component non-conforming, including a behaviour that becomes required.
- **Requirement IDs and case IDs are stable**: never renumbered, never reused. A new requirement takes the next free number in its chapter.
- **Order of a change**, fixed: (1) change the text and schemas here; (2) add vectors; (3) add suite cases and see them fail against a broken fixture; (4) the three SDKs implement it, each fixture component passing; (5) tag.
- **Who pins whom**: `be-acceptance` pins one exact protocol version; `be-sdk-go` imports this module in its tests; `be-sdk-python` and `be-sdk-ts` copy `vectors/` and `schemas/` from a tag (`make sync-vectors`) and check `vectors/SHA256SUMS`. Copying test data is not importing code.
- **Family contracts are versioned on their own** (`brickKit/contract-infra-authz`, `brickKit/contract-infra-iam`). This text names only their major, for example `contract: authz/2.x`.

See [CHANGELOG.md](CHANGELOG.md).

## License

Apache License 2.0, see [LICENSE](LICENSE).
