[English](README.md) · [中文](README.zh.md)

# Vectors

Language-neutral test vectors for the parts of the component protocol that are pure computation: given this input, every implementation must produce exactly this output or exactly this error. Every official SDK runs them in its unit tests (Go imports this repository; Python and TypeScript copy `vectors/` with `make sync-vectors` and check `SHA256SUMS`). A component in a fourth language SHOULD run them. They are not run against containers: that is the component conformance suite in `tools/be-acceptance/conformance/component/`.

## Areas

| Area | What it pins down | Protocol | Files | Cases |
|---|---|---|---|---|
| [money](money/README.md) | decimal strings, column capacity, ISO 4217 minor units, rounding modes, cash rounding, allocation, tax per line / per document, currency pairing, conversion, line amounts | P11.6 | 8 + `iso4217.json` | 240 |
| [idempotency](idempotency/README.md) | the request fingerprint (RFC 8785 + SHA-256), the replay / mismatch / in-progress decision, key sources, caller namespaces, expiry | P3.7, P13 | 3 | 101 |
| [envelope](envelope/README.md) | UUIDv7 ids, CloudEvents headers from an outbox row, causation and hop count, inbound acceptance and dead letters, the state-mode cursor, redelivery, stream / durable / dead-letter names | P11.5, P12 | 6 | 118 |
| [calendar](calendar/README.md) | business date of an instant in a legal entity's zone (DST, unusual offsets, skipped days), day and range bounds, fiscal periods and years with any start month | P11.7, P11.9 | 3 | 93 |
| [numbering](numbering/README.md) | document number formats, the period a format resets on, the gap-free and gapped allocation models | P11.10 | 3 | 46 |
| [errors](errors/README.md) | gRPC code ↔ HTTP status, platform reasons, restoring a dependency's REST error, SQLSTATE classification, log levels, the problem+json body, `Retry-After`, reason names | P4, P10.4 | 4 | 123 |
| [config](config/README.md) | typed parsing of configuration values, defaults and presence, durations, booleans, secret files, dependency address variables, slot-family addresses, key names and secret declarations, value forms in `config/*.yaml` (including `$endpoint:`) | P2 | 4 | 196 |
| [redaction](redaction/README.md) | which log field keys are personal data and how they are redacted | P18.2 | 1 | 29 |
| authz | bundle evaluation, levels, dimensions, subject sets | P6 | — | in `contract-infra-authz` (lane K1); copied here when it is released |
| lifecycle, search | lifecycle planner, search normalisation | P16, data-platform §7.4 | — | later |

Total: 946 cases in 32 case files.

## Case file format

One JSON file per topic, `vectors/<area>/<topic>.json`, described by [case-file.schema.json](case-file.schema.json):

| Field | Meaning |
|---|---|
| `area`, `topic` | the directory and the file name |
| `protocol` | the protocol version whose semantics the file pins (`1.0`) |
| `generated_by` | the generator script; the file is never edited by hand |
| `notes` | optional facts about the generation (tz database version, ISO 4217 publication date) |
| `cases[].id` | `<area>.<topic>.<slug>`, stable for ever: never renamed, renumbered or reused |
| `cases[].description` | one sentence: what the case is about |
| `cases[].op` | the operation; each area's README lists its operations and their input and output shapes |
| `cases[].refs` | protocol clauses (`P11.6`) or RFC sections the case illustrates |
| `cases[].input` | the operation's input |
| `cases[].expected` | the exact output, compared by deep equality |
| `cases[].expected_error.reason` | the error the operation must fail with, instead of `expected` |

Exactly one of `expected` and `expected_error` is present.

## How an SDK runs them

1. For each file, for each case, dispatch on `op` to the SDK function it names (each area's README maps operations to the SDK API).
2. With `expected`: the function must succeed and its result, rendered in the shape the README gives, must deep-equal `expected`.
3. With `expected_error`: the function must fail, and the SDK's error must carry that reason. The reasons in `expected_error` are **vector error classes**, listed per area with the wire error they become; where one is also a platform reason (`IDEMPOTENCY_MISMATCH`), the names are the same.
4. A failing vector is a bug in the SDK, never in the vector, until a person decides otherwise (06-testing's iron rule). A wrong vector is changed in the generator, in its own commit, saying why.

Go: `besdktest.Vectors(t, dir, run)` walks a directory. Python and TypeScript: a parametrised test per file.

## Rules for implementers that the vectors exposed

- **Anchor every pattern to the whole string.** Python's `re.match(r"…$")` accepts a trailing newline; `"12\n"` passed as a decimal until the Go cross-check caught it. Use `re.fullmatch`, Go's `^…$`, JavaScript's `^…$` without the `m` flag.
- **Numbers in JSON are IEEE 754 doubles.** Every integer in these files is within ±(2^53−1) (I-JSON, RFC 7493 §2.2). A 64-bit value, such as a duration in nanoseconds, is written as a decimal string.
- **Library defaults are broader than the protocol**: Go's `strconv.ParseBool` accepts `TRUE` and `t`, `strconv.ParseInt` accepts `+5`, `net/url` lower-cases the scheme, Python's `decimal.Decimal` accepts `1_000`, surrounding spaces, `1e5`, `NaN` and full-width digits, Python's `json` accepts `NaN`, JavaScript's `Intl` accepts `asia/shanghai` and `+08:00` as time zones, and the npm `canonicalize` package prints a non-finite number as `null`. The vectors include a case for each.

## Generation and cross-check

Every expected value is computed by a generator, `vectors/<area>/gen/gen_<area>.py` (Python ≥ 3.11, standard library only, deterministic), and recomputed by an independent second implementation that shares no code with it:

| Area | Second computation |
|---|---|
| money | Go, `math/big.Rat` (`gen/xcheck_money.go`); the ISO table is also checked against a list typed in by hand |
| idempotency | Node, the npm package `canonicalize` (RFC 8785 reference by its authors) and `node:crypto` |
| envelope, numbering, redaction | Node, written separately from the protocol text |
| calendar | Node, `Intl.DateTimeFormat` over ICU's time-zone data (the generator uses Python `zoneinfo` over the system tz database) |
| errors | Go, tables typed in again from foundations 15 |
| config | Go, the real `time.ParseDuration`, `net/url`, `encoding/json` with the protocol's rules layered on top |

```sh
cd vectors
make gen       # regenerate
make xcheck    # cross-check in throwaway golang:1.22-alpine / node:22-alpine containers
make sums      # rewrite SHA256SUMS
```

Last run (2026-10-03): 946 cases, 0 disagreements; tz database 2026c on both sides; ISO 4217 List One published 2026-09-17. Disagreements found and fixed during the first run: one (the trailing-newline case above).

## Versioning

- Adding a case, or a file, is a patch release of be-protocol.
- Changing an expected value changes semantics: it follows the protocol's minor / major rules (the repository README, "Versioning"), and the case keeps its id only if the old behaviour was a bug.
- `SHA256SUMS` lists every vector file; the Python and TypeScript SDKs verify it after copying.
