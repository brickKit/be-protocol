[English](00-reading-the-spec.md) · [中文](00-reading-the-spec.zh.md)

# Reading the specification

Terms, requirement levels and identifiers used by every chapter. Read this once before any chapter.

## Terms

| Term | Means |
|---|---|
| component | a BrickKit component of a BrickEnterprise project: one image, one `component.yaml`, one `assembly.yaml`, ID `<domain>/<name>` |
| member | one component hosted inside a shell process. Unless a rule says otherwise, every rule for a component applies to each member, and a member behaves exactly as the same component standalone |
| shell | one process that hosts several members of one language ([P19](19-shells.md)) |
| runtime | the code inside a component that implements this protocol: an official SDK, or the component's own code in another language |
| main port | the HTTP port of `deployment.port` (standalone) or the member's `httpPort` (shell) |
| system plane | gRPC between components ([P7](07-system-rpc.md)); every caller on it is a system principal |
| user plane | REST that people reach through the edge ([P3](03-http-surface.md)) |
| `besdk_*` table | a table the runtime owns inside the component's schema ([ddl/](../ddl/)); component SQL never reads or writes one |
| profile | a named group of conformance cases, selected from the component's manifests (README, *Conformance*) |
| suite | the black-box conformance suite `conformance/component/` of `brickKit/be-acceptance` |
| deadline | the time by which the current unit of work must finish; it only shrinks as work travels ([P9](09-deadlines-and-retries.md)) |
| the platform | brickKit (≥ v1.4.0): it evaluates configuration (`$var:`, `$endpoint:`, `${VAR}`, `file://`), injects it and the `*_ENDPOINT` variables, mounts secret files, generates deployment files and starts containers |

Durations use Go duration syntax (`200ms`, `5s`, `15m`, `1h`); sizes are binary (1 MiB = 1,048,576 bytes); instants are RFC 3339 in UTC; business dates are `YYYY-MM-DD`.

## Requirement levels

The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are to be read as described in RFC 2119 and RFC 8174 when, and only when, they appear in capitals.

| Level in the tables | Meaning | Who checks it |
|---|---|---|
| **MUST** | required for conformance; observable from outside | the suite; a failure fails the run |
| **SHOULD** | recommended; a component may deviate with a reason | the suite warns |
| **MAY** | optional surface | — |
| **INTERNAL** | required for conformance (as MUST), but not observable from outside the process, for example "no network call inside a transaction" | an official SDK's own tests; for another language, the component's `AGENTS.md` states how it is kept and review checks it |

A row marked **MUST, partly INTERNAL** has an observable part that the suite tests and an internal part that review checks; the row says which is which.

## Identifiers

- **Requirement IDs** are `P<chapter>.<n>`, for example `P7.5`. They are stable across protocol versions: never renumbered, never reused, never given a new meaning. A requirement withdrawn in a later major keeps its row, marked withdrawn. A new requirement takes the next free number of its chapter.
- **Case IDs** are `CP-<GROUP>-<nn>`, for example `CP-AUTH-03`, the suite case that tests a requirement. Groups: `CORE`, `OBS`, `ERR`, `AUTH`, `SCOPE`, `RPC`, `OUT`, `EVP`, `EVS`, `IDEM`, `DB`, `JOBS`, `LIFE`, `BLOB`, `SHELL`. Case IDs are append-only too. The full list, with the profile each belongs to and the requirement it tests, is [`schemas/conformance-cases.yaml`](../schemas/conformance-cases.yaml).
- **Reasons** of domain `be` (`TOKEN_INVALID`, `DB_POOL_EXHAUSTED`, …) are listed in [`schemas/errors-be.yaml`](../schemas/errors-be.yaml); the text names them in code font.

## What the protocol does not cover

- Business behaviour: a component's own state machines, its own reasons, its own events.
- The family contracts of slot families: the authorization provider (`brickKit/contract-infra-authz`, major `authz/2`) and the identity provider (`brickKit/contract-infra-iam`, major `iam/1`). This text says only how a component consumes them.
- brickKit itself: `component.yaml`, the injected variables and deployment generation are brickKit's contract; this text relies on them and adds no field to `component.yaml`; it only requires some of brickKit's fields to be declared ([P20](20-self-description-and-versioning.md#what-componentyaml-declares)).
- Any one language's API. Function names in official SDKs are in their own documentation.
