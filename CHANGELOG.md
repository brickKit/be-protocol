[English](CHANGELOG.md) · [中文](CHANGELOG.zh.md)

# Changelog

Release tags are `vMAJOR.MINOR.PATCH`; the protocol version a component declares is `MAJOR.MINOR` (README, *Versioning*).

## v1.0.0-rc.1

First release candidate of protocol 1.0. Not frozen: the pilot components may still change it before `v1.0.0`.

- Specification P1–P20 (`spec/`), English with Chinese mirrors; requirement IDs `P<chapter>.<n>` and case IDs `CP-<GROUP>-<nn>` fixed from here on.
- Schemas (`schemas/`): configuration key catalogue, the `be` reason catalogue, problem body, event envelope, event contract file, access-token claims, `lifecycle.yaml` v1, `DATA_LIFECYCLE`, `JOBS_OVERRIDES`, the protocol keys of `assembly.yaml`, `/_be/info`, `conformance/fixtures.yaml`, the conformance case catalogue and the suite report.
- Reference DDL (`ddl/`) of every `besdk_*` table and the runtime's `SECURITY DEFINER` functions, checked on PostgreSQL 14 and 16; reference DDL of the PostgreSQL queue bus adapter (`be_bus`).
- `proto/be/v1/limits.proto` (`max_items`), `proto/be/lifecycle/v1/lifecycle.proto`; OpenAPI fragments for the operations endpoints, `_authz` / `_shares` and `_lifecycle`.
- Semantic vectors (`vectors/`) and the fixture component `conformance/widget` (`fixtures/widget/`).
- Reconciled before tagging (phase A): slot-family addresses and the derived gRPC target, family keys (`IAM_URL`, `BOOTSTRAP_ADMIN_LOGIN`, P2.10, P2.11); 33 reasons of domain `be` (`RATE_LIMITED`, `UPSTREAM_*`, `NETWORK_IN_TX`, `NESTED_TX`, `DB_TOO_MANY_CONNECTIONS`); subject segments and injective durable names (`.` → `__`); runtime-side redelivery and dead-lettering, create-if-absent durables (CP-EVS-08); `@every` schedules; normative redaction with `authorization`, `cookie`, `set_cookie`, `api_key`; `besdk_number_allocations`; thaw through `SECURITY DEFINER` functions; the `/* be:<schema> */` statement prefix; calendar degraded mode and embedded tz data in `/_be/info`; fixture fields for every fact the suite needs; `make check`. Vector case IDs `envelope.cursor.last-delivery` and `envelope.cursor.conformance-last` became `last-allowed-failure` and `conformance-last-allowed` (their meaning changed; nothing was released under the old IDs).
