[English](README.md) · [中文](README.zh.md)

# Vectors: config

How a component parses its configuration at start, how dependency addresses are named and read, which key names it may declare, and which value forms `config/*.yaml` may use (protocol P2; foundations 24; brickKit's environment-variable contract). SDK API: Go `Runtime.Config` (typed getters, `Endpoint(dep, port)`), the secret source; `forms.json` is for be-ops and the gates, not for the SDKs.

## Files

| File | Cases | Operations |
|---|---|---|
| `values.json` | 92 | `parse_value`, `read_undeclared` |
| `endpoints.json` | 25 | `endpoint_name`, `endpoint_value`, `family_url` |
| `keys.json` | 19 | `key_name` |
| `forms.json` | 20 | `value_form` |

## Operations

| Op | Input | Expected |
|---|---|---|
| `parse_value` | `type` (`string`, `integer`, `boolean`, `duration`, `duration_list`, `url`, `json`, `enum`), `value` (the environment value; `null` = the variable does not exist), optional `default`, `required`, `secret`, `minimum`, `schemes`, `json_kind`, `enum` | `set: false`, or `set: true` with `value`; for `secret: true` also `source: env` (with `value`) or `source: file` (with `path`) |
| `read_undeclared` | `key`, `declared[]` | `allowed: true` for platform names |
| `endpoint_name` | `dependency`, `port` (`""` = the main port) | `name` of the injected variable |
| `endpoint_value` | `value` (or `null`) | `present: false`, or `present: true` with `address` (`host:port`) |
| `family_url` | `value` of a slot family's `*_URL` (`AUTHZ_URL`, `IAM_URL`) | `base` (`http://host:port`, REST paths are appended) and `grpc_target` (`host:(port + 1000)`), P2.10 |
| `key_name` | `key` | `valid: true` |
| `value_form` | `written` (a string or `{existingSecret, key}`), `secret` | `form`: `literal`, `var`, `env` (with `name`, optional `default`), `template` (with `names`), `file` (with `path`), `existing_secret` |

## Rules

- **Presence**: a variable that does not exist takes the `default`, or is `CONFIG_MISSING` when required, or is not set. An empty value counts as not set for every type except `string` (brickKit's `${NAME:-}`). A present value that does not parse is `CONFIG_INVALID`; it never falls back to the default, and a default that does not parse is an error too.
- **integer**: `^-?[0-9]+$` (leading zeros are decimal), within ±(2^53−1) so every language holds it exactly; no `+`, spaces, separators, hex, exponent or non-ASCII digits.
- **boolean**: exactly `true`, `false`, `1`, `0`.
- **duration**: Go's `time.ParseDuration` syntax (`5s`, `1h30m`, `1.5h`, `200ms`, `10us` / `10µs` / `10μs`, `7ns`, `.5s`, `+5s`, a bare `0`); no day unit, no upper case, no spaces, no ISO 8601; negative durations are rejected. The value is in nanoseconds, written as a decimal string.
- **duration_list**: comma-separated durations, no spaces, no empty element, each positive (`EVENTS_BACKOFF`).
- **url**: `scheme://host[:port][path]`, lower-case scheme, one host, port 1–65535, no whitespace; `schemes` restricts the scheme for a key (`EVENT_BUS_URL`: `nats`, `postgres`, `kafka`). The value is returned unchanged.
- **json**: I-JSON (duplicate names and `NaN` rejected); `json_kind` requires an object or an array (`JOBS_OVERRIDES` is an object).
- **enum**: exact, case-sensitive (`LOG_LEVEL`).
- **secrets**: for a `secret: true` key, `@file:/absolute/path` selects the file source (re-read when it changes); anything else is the value from the environment. For other keys `@file:` is ordinary text.
- **Undeclared keys**: reading a key that is neither declared in `configSchema` nor a platform name (`COMPONENT_ID`, `COMPONENT_VERSION`, `PORT`, `*_ENDPOINT`) is `CONFIG_UNDECLARED`.
- **Address variables**: `<dependency id upper-cased, / and - as _>[_<PORT NAME>]_ENDPOINT`. An absent optional dependency has no variable at all (`present: false`); an empty value is a configuration error. The value is `http://host:port[/]`; the SDK strips `http://` and a trailing `/`; anything else is `CONFIG_INVALID`.
- **Key names**: `^[A-Z][A-Z0-9_]*$`; `COMPONENT_ID`, `COMPONENT_VERSION`, `PORT`, `BRICKKIT_SERVED_MEMBERS*` and every `*_ENDPOINT` belong to the platform.
- **Value forms** (be-ops, gates): `$var:NAME` must be the whole value; `${NAME}` or `${NAME:-default}` (references never nest); a template may embed `${NAME}`; `file://` paths are relative to the project and stay inside it; `existingSecret` is for `secret: true` items only. **A secret is only ever a reference**: a literal, a template or a non-empty plaintext default for a `secret: true` item is rejected.

## Errors

| Class | When |
|---|---|
| `CONFIG_MISSING`, `CONFIG_INVALID`, `CONFIG_UNDECLARED` | at start: exit code 78 with one JSON log line naming the key (P1.2); in a shell all members' errors are collected first |
| `COMPONENT_INVALID`, `PORT_NAME_INVALID` | malformed dependency id or port name |
| `CONFIG_KEY_INVALID`, `CONFIG_KEY_RESERVED` | a key a component may not declare (gate) |
| `FORM_INVALID`, `FORM_NOT_FOR_PLAIN`, `SECRET_NOT_REFERENCE`, `SECRET_PLAINTEXT_DEFAULT` | a value form the project does not accept (gate) |

## Decided here

For review: empty means not set for typed keys; integers are limited to ±(2^53−1); booleans are `true` / `false` / `1` / `0` only (not Go's wider `ParseBool` set); negative durations are rejected; duration lists allow no spaces; endpoint values other than `http://host:port[/]` are rejected; a secret written as a template or with a plaintext default is rejected.

## Regenerate

`python3 gen/gen_config.py`; cross-check `go run gen/xcheck_config.go .` (it also prints where Go's own helpers are broader than the protocol).
