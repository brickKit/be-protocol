[English](19-shells.md) · [中文](19-shells.zh.md)

# P19 Shells

What a shell launcher and its members must do so that N processes become one and nothing else changes. A shell exists only for a language with an official SDK and that SDK's launcher; a member behaves exactly as the same component standalone.

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P19.1 | MUST | A shell hosts members of **one language and one SDK version**, compiled or linked into the shell's image. At start it reads `BRICKKIT_SERVED_MEMBERS_CONFIG` (missing, empty or `null` is an error; `[]` means zero members). A listed member that is not compiled in, or is compiled at a version other than the listed one (Go build info, Python `importlib.metadata`, the member package's `package.json`), makes the shell exit with code **2**, naming the member | CP-SHELL-01, CP-SHELL-02 |
| P19.2 | MUST | Each member uses its own entry's `config`, `httpPort` and `extraPorts`: its own HTTP server and its own gRPC server with its own interceptor chain. Members call each other over the network exactly as standalone; there is no in-process transport | CP-SHELL-08 |
| P19.3 | MUST | Exactly four things are process-wide: the OpenTelemetry exporter and propagator (the shared exporter is shut down only by the shell, after every member has stopped; stopping a member flushes only that member's own span queue); the token verifier (JWKS) and the bundle; the physical database pool; the bus connection. They can be shared only because every member's `AUTHZ_URL`, `IAM_URL`, `IAM_ISSUER`, `TENANT_ID`, `PG_HOST`, `PG_PORT`, `PG_DATABASE` and `EVENT_BUS_URL` (or `NATS_URL`) equal the shell's own; any difference makes the shell exit with code **78**, naming the member and the key. All members' configuration errors are reported together | CP-SHELL-03 |
| P19.4 | MUST | Everything else is per member: configuration, logger, metrics registry, tracer and meter providers (`service.name` = the member's ID), the database store (the member's identity and connection budget), gRPC connections and the outbound bulkhead, durables and subscriptions, jobs, caches, the authorization projection, the lifecycle engine, advisory-lock keys | CP-SHELL-04, CP-SHELL-05 |
| P19.5 | MUST | The shell's login role is NOINHERIT towards its members: it holds no member's privileges and reaches a member's role only through `SET LOCAL ROLE`, granted with `GRANT <member role> TO <shell role> WITH INHERIT FALSE, SET TRUE`; a shell therefore requires PostgreSQL ≥ 16 (standalone components keep 14 as the floor). Every background path works under it. Isolation between members is the runtime's job, not the database's: the shell role may switch to every member's role, so only the runtime's store issues `SET LOCAL ROLE`, always to the member's own runtime role `PG_USER` (never to an owner role, which the shell is never granted), and member code never issues `SET ROLE` ([P10.1](10-database.md)) | CP-SHELL-07 |
| P19.6 | MUST | The shell's `/healthz` answers for the shell process only. A member whose initialisation fails makes the whole shell fail to start (non-zero). A member's failing background work is restarted by the same supervisor as standalone; it never stops for good and never ends the process | CP-SHELL-06 |
| P19.7 | MUST | The shell serves on its own port `/healthz` and one aggregated `/metrics` of every member's registry with `component` labels; each member's own `/metrics` stays available on its port | CP-SHELL-04 |
| P19.8 | MUST | Migrations run from each member's own image before the shell starts, never inside the shell | — |
| P19.9 | MUST | The shell declares its own `deployment.stopGracePeriodSeconds` (brickKit uses the shell's value as it is and derives nothing from the members'), at least the largest value of any member it is built with, and its own `SHUTDOWN_GRACE` at least the largest member's. On `SIGTERM` it stops its members concurrently, so stopping takes as long as the slowest member, and exits within that period | CP-SHELL-11 |
| P19.10 | MUST | The shell declares `readinessCheck: {type: http, path: /readyz}` ([P1.11](01-process-and-lifecycle.md)). Its `/readyz` on its own port answers `200` only when every hosted member is ready (P1.4, with the same latching); otherwise `503` `NOT_READY` with `metadata.waiting` listing the component IDs of the members not ready yet, comma-separated. With zero members it answers `200`. Each member's own `/readyz` stays available on its port | CP-SHELL-11 |

## Input

| Variable | Content |
|---|---|
| `BRICKKIT_SERVED_MEMBERS` | the service names of the hosted members, comma-separated, set by brickKit |
| `BRICKKIT_SERVED_MEMBERS_CONFIG` | one JSON array, one item per member: `componentId`, `version`, `httpPort`, `extraPorts` (`[{"name": "grpc", "port": 9095}]`) and `config` (the member's keys with values already evaluated, including its `*_ENDPOINT` variables and its `$endpoint:` values; a secret key's value is the path of its file, `/run/brickkit/secrets/<member's service name>/<KEY>`, which brickKit mounts into the shell's container, so the shell hands `config` over as it is; `componentId` and `version` stand in for `COMPONENT_ID` and `COMPONENT_VERSION`) |

The shell's own keys (its `PG_USER` login role, `PG_POOL_MAX` = the physical pool size, default 40, and the shared addresses of P19.3) come from its own configuration as in [P2](02-configuration.md).

## Launch sequence

1. Parse `BRICKKIT_SERVED_MEMBERS_CONFIG` and the shell's own configuration (P19.1).
2. For each member: compiled in and at the listed version (exit 2 otherwise); shared keys equal to the shell's (exit 78 otherwise); its configuration valid (all errors together, exit 78).
3. Create the process-wide four (P19.3); size the pool `min(Σ members' PG_POOL_MAX, shell PG_POOL_MAX)`.
4. For each member: a runtime of its own (P19.4), its initialisation (failure ends the shell), its servers on its ports, its supervised background work.
5. Serve `/healthz`, `/readyz` (P19.10) and the aggregated `/metrics` on the shell's port.
6. On `SIGTERM`: stop accepting, stop the members concurrently ([P1.6](01-process-and-lifecycle.md), P19.9), close the shared resources, exit 0.

## Notes

- Running every member standalone must behave the same as running them merged; `brickkit up --ignore-shells` is how a project checks it.
- The shell opens every member's ports, so a deploy entry may `expose` a member (brickKit ≥ v1.2.0): on Docker / Podman the shell's container publishes the member's main port; on Kubernetes the member's own Ingress points at the member's own Service, which selects the shell's Pod. A member entry's `replicas`, `resources` and `labels` do not apply: the shell is one process.
- A shell restart takes every member down at once; durable consumers keep their position, reconcilers resume in-flight flows, and retry budgets absorb the gap.
