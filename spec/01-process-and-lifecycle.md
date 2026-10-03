[English](01-process-and-lifecycle.md) · [中文](01-process-and-lifecycle.zh.md)

# P1 Process and lifecycle

How a component's process starts, reports health, shuts down, survives its own errors and exits. Applies standalone and to each member of a shell; shell-specific additions are in [P19](19-shells.md).

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P1.1 | MUST | The image has two entry points. The default command serves. The command in `component.yaml` `migration.command` runs the migrations and exits 0 on success. Both use the same image and the same configuration. The platform runs the migration command before every start, so it MUST be idempotent: run twice in a row, both runs exit 0 and the second changes nothing ([P11](11-migrations-and-data-shapes.md)). Official SDKs use one binary with sub-commands: `[<binary>, migrate, up]` migrates, `[<binary>]` serves; `migrate status`, `migrate down <n>` and, when offered, `job run <name>` ([P14.8](14-background-jobs.md)) are also there. An argument the entry point does not recognise exits **64** at once, before the configuration is read, so a misspelt migration command can never become a second server | CP-CORE-01 |
| P1.2 | MUST | Start order is fixed: (1) read and validate the configuration ([P2](02-configuration.md)); (2) open the ports; (3) connect to PostgreSQL, the event bus, the authorization provider and the JWKS **in the background**. A missing required key, a value that does not parse, or a component ID that differs from the injected `COMPONENT_ID` prints one JSON log line per problem naming the key, and the process exits with code **78** (EX_CONFIG). `COMPONENT_ID` absent from the environment means the process was not started by the platform: it exits **64** at once, like an unrecognised argument. A dependency that is not reachable yet is retried with backoff (0.5 s doubling to 15 s); the process does not exit | CP-CORE-02, CP-CORE-03 |
| P1.3 | MUST | `GET /healthz` and `HEAD /healthz` on the main port answer `200` whenever the process is alive and serving. The handler touches no dependency: not PostgreSQL, not the bus, not the authorization provider, not another component. Stopping PostgreSQL does not change its answer | CP-CORE-04 |
| P1.4 | MUST | `GET /readyz` on the main port answers `200` once all of: a first authorization bundle was loaded (only when the component has protected routes); the database identity probe passed ([P10.7](10-database.md)); the schema's migration version equals the image's. Otherwise `503` with a problem body, reason `NOT_READY`, and `metadata.waiting` listing what is missing (`bundle`, `db_identity`, `migrations`), comma-separated. A condition once met stays met: a later outage of PostgreSQL, the bus, the authorization provider or another component never turns `/readyz` back to `503` (the bundle is kept fail-static, [P6.1](06-authorization.md)), so a downstream hiccup never takes every replica out of service. The platform probes it through `readinessCheck` (P1.11): Kubernetes routes traffic to a Pod only once it answers `200`, and on Docker / Podman dependents start only then | CP-CORE-05 |
| P1.5 | MUST | Before the first bundle is loaded, every route that is not Public, Authenticated routes included, first verifies the token (a missing or invalid one answers `401` `TOKEN_INVALID`, [P5](05-identity.md)) and then answers `503` with reason `AUTHZ_NOT_READY`, because the stale and delegation checks need the bundle ([P6.2](06-authorization.md)). Public routes serve normally | CP-AUTH-10 |
| P1.6 | MUST | On `SIGTERM`: stop accepting new requests and new deliveries; let in-flight requests finish within `SHUTDOWN_GRACE` (default 25 s); then stop background work: cancel job runs, release leases, ack or nak in-flight messages, finish the outbox pump's current batch; then exit **0**. `SHUTDOWN_GRACE` (default 25 s) plus the background stop fits inside the platform's stop grace period (P1.12), so the platform never has to kill the process | CP-CORE-06 |
| P1.7 | MUST | A recoverable error never ends the process. Every piece of background work (jobs, workers, reconcilers, consumers, the outbox pump, projection pulls, bundle polling) is supervised: a failure or panic is recovered, logged and counted, and the work restarts with exponential backoff from 1 s to 5 min; one piece stopping never stops another. Standalone and shell behave identically | CP-JOBS-05, CP-SHELL-06 |
| P1.8 | MUST | A fatal error exits with a **non-zero** code: invalid configuration (78); a schema whose migration version is newer than the image's, on the serve entry point (the migrate entry point instead logs a WARN and exits 0, so that rolling back to an older image is not blocked by its migration step); a required database capability missing ([P10.7](10-database.md)); a shell member that is not compiled in or is compiled at another version (2, [P19.1](19-shells.md)); the component's one-time initialisation failing or exceeding 30 s. A process never exits 0 after a failed initialisation | CP-SHELL-01, CP-SHELL-02 |
| P1.9 | MUST | The image contains `/bin/sh` and `wget`: the platform runs the health check through the shell. `scratch` and distroless bases are not conforming | CP-CORE-07 |
| P1.10 | MUST | The component's one-time initialisation (the module's start hook) performs setup only and returns; it never starts a loop. Recurring work is declared as a job ([P14.1](14-background-jobs.md)) | — (INTERNAL, see P14.1) |
| P1.11 | MUST | `component.yaml` declares both checks, which brickKit (≥ v1.3.1) turns into the engines' probes: `healthCheck: {type: http, path: /healthz}` (liveness and start-up) and `readinessCheck: {type: http, path: /readyz}` (readiness). A component whose start-up exceeds the platform's 60 s default sets `healthCheck.startPeriodSeconds` | CP-CORE-12 |
| P1.12 | MUST | `component.yaml` declares `deployment.stopGracePeriodSeconds`, the time from the stop signal to the kill: **30** unless the component needs more, and always at least `SHUTDOWN_GRACE` + 5 s, so the process finishes P1.6 and exits by itself. brickKit writes it as compose `stop_grace_period` and Kubernetes `terminationGracePeriodSeconds`; a deploy entry may override it, keeping the same margin. A shell declares its own value ([P19.9](19-shells.md)) | CP-CORE-06, CP-CORE-12 |
| P1.13 | MUST | Every port listens on all interfaces, IPv4 and IPv6 (`0.0.0.0` and `::`, or one dual-stack `::` socket): the platform's health check calls `127.0.0.1` inside the container, Kubernetes probes the Pod IP, and a caller may resolve a service name to either family. A process that listens on IPv4 only, or on `localhost` only, is not conforming | CP-CORE-13 |

## Exit codes

| Code | When |
|---|---|
| 0 | clean shutdown after `SIGTERM`; a migration run that succeeded or had nothing to do |
| 2 | a shell refused its member list ([P19.1](19-shells.md)) |
| 64 | usage error: an argument the entry point does not recognise (P1.1), `job run` with an unknown job name ([P14.8](14-background-jobs.md)), or no `COMPONENT_ID` in the environment (P1.2) |
| 78 | configuration error: missing or unparsable key, component ID mismatch, a shell member's shared key that differs from the shell's |
| any other non-zero | any other fatal error ([P1.8](#requirements)) |

## Operations endpoints

All on the main port, never routed by the edge, no authentication:

| Path | Answers | Defined in |
|---|---|---|
| `GET`, `HEAD /healthz` | `200` while alive; body empty or `ok` | P1.3 |
| `GET /readyz` | `200` or `503` problem `NOT_READY` | P1.4, P1.11 |
| `GET /metrics` | Prometheus text format | [P18.3](18-observability.md) |
| `GET /_be/info` | self-description JSON | [P20](20-self-description-and-versioning.md) |

Their shapes are in [`openapi/ops.yaml`](../openapi/ops.yaml).

## Notes

- `/healthz` answers only for the process because a downstream hiccup would otherwise restart every upstream, and in a shell every member at once.
- Exit code 78 lets an operator tell "fix the configuration" from "the program crashed" without reading logs.
- Liveness and readiness are two questions with two consequences: a failed liveness check restarts the container, a failed readiness check only keeps traffic away. `/readyz` answers "could this process serve yet", which is why it waits for the first bundle and why, once ready, it never fails because of something outside the process.
- The stop grace period is a fact about the component (how long its in-flight work takes), so the component declares it; `SHUTDOWN_GRACE` is the runtime's own budget inside it.
