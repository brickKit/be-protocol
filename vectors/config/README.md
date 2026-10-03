[English](README.md) · [中文](README.zh.md)

# Vectors: config

How a component parses its configuration at start, how dependency and slot-family addresses are named and read, how a secret file is read, which key names it may declare and how it declares a secret, and which value forms `config/*.yaml` may use (protocol P2; foundations 24; brickKit's environment-variable contract). SDK API: Go `Runtime.Config` (typed getters, `Endpoint(dep, port)`, the family addresses), the secret source; `forms.json` is for be-ops and the gates, not for the SDKs.

## Files

| File | Cases | Operations |
|---|---|---|
| `values.json` | 104 | `parse_value`, `read_undeclared`, `secret_text` |
| `endpoints.json` | 31 | `endpoint_name`, `endpoint_value`, `family_address` |
| `keys.json` | 29 | `key_name`, `key_declaration` |
| `forms.json` | 32 | `value_form` |

## Operations

| Op | Input | Expected |
|---|---|---|
| `parse_value` | `type` (`string`, `integer`, `boolean`, `duration`, `duration_list`, `url`, `json`, `enum`), `value` (the environment value; `null` = the variable does not exist), optional `default`, `required`, `secret`, `minimum`, `schemes`, `json_kind`, `enum` | `set: false`, or `set: true` with `value`; for `secret: true`, `source: file` with `path` (the variable holds the file's path, P2.7) |
| `read_undeclared` | `key`, `declared[]` | `allowed: true` for platform names |
| `secret_text` | `content` (the text of a secret file), `required` | `set: false`, or `set: true` with `value` (P2.9) |
| `endpoint_name` | `dependency`, `port` (`""` = the main port) | `name` of the injected variable |
| `endpoint_value` | `value` (or `null`) | `present: false`, or `present: true` with `address` (`host:port`) |
| `family_address` | `key` (`AUTHZ_URL`, `AUTHZ_GRPC_URL`, `IAM_URL`, `IAM_GRPC_URL`), `value` (or `null`) | `present: false`, or `present: true` with `base` (`http://host:port`, REST paths are appended) for a `*_URL` key, or `target` (`host:port`, the gRPC dial target) for a `*_GRPC_URL` key, P2.10 |
| `key_name` | `key` | `valid: true` |
| `key_declaration` | `key`, optional `secret`, `mount`, `type` (a `configSchema` item) | `valid: true` (P2.12) |
| `value_form` | `written` (a string or `{existingSecret, key}`), `secret` | `form`: `literal`, `var`, `env` (with `name`, optional `default`), `template` (with `names`), `file` (with `path`), `existing_secret`, `endpoint` (with `component`, optional `version`, `port`, `path`) |

## Rules

- **Presence**: a variable that does not exist takes the `default`, or is `CONFIG_MISSING` when required, or is not set. An empty value counts as not set for every type except `string` (brickKit's `${NAME:-}`). A present value that does not parse is `CONFIG_INVALID`; it never falls back to the default, and a default that does not parse is an error too.
- **integer**: `^-?[0-9]+$` (leading zeros are decimal), within ±(2^53−1) so every language holds it exactly; no `+`, spaces, separators, hex, exponent or non-ASCII digits.
- **boolean**: exactly `true`, `false`, `1`, `0`.
- **duration**: Go's `time.ParseDuration` syntax (`5s`, `1h30m`, `1.5h`, `200ms`, `10us` / `10µs` / `10μs`, `7ns`, `.5s`, `+5s`, a bare `0`); no day unit, no upper case, no spaces, no ISO 8601; negative durations are rejected. The value is in nanoseconds, written as a decimal string.
- **duration_list**: comma-separated durations, no spaces, no empty element, each positive (`EVENTS_BACKOFF`).
- **url**: `scheme://host[:port][path]`, lower-case scheme, one host, port 1–65535, no whitespace; `schemes` restricts the scheme for a key (`EVENT_BUS_URL`: `nats`, `postgres`, `kafka`). The value is returned unchanged.
- **json**: I-JSON (duplicate names and `NaN` rejected); `json_kind` requires an object or an array (`JOBS_OVERRIDES` is an object).
- **enum**: exact, case-sensitive (`LOG_LEVEL`).
- **secrets**: a `secret: true` key is declared `mount: file` and named `…_FILE`; its variable holds the **absolute path** of the file brickKit mounted (`/run/brickkit/secrets/<service>/<KEY>`, a host path for `mode: local`); a relative path, a directory or a value is `CONFIG_INVALID`. The file's text is the value with exactly one trailing LF or CRLF removed (`secret_text`); an empty result is not set (`CONFIG_MISSING` when required). The runtime re-reads the file when it changes (P2.9). For other keys a path is ordinary text.
- **Undeclared keys**: reading a key that is neither declared in `configSchema` nor a platform name (`COMPONENT_ID`, `COMPONENT_VERSION`, `PORT`, `*_ENDPOINT`) is `CONFIG_UNDECLARED`.
- **Address variables**: `<dependency id upper-cased, / and - as _>[_<PORT NAME>]_ENDPOINT`. An absent optional dependency has no variable at all (`present: false`); an empty value is a configuration error. The value is `http://host:port[/]`; the SDK strips `http://` and a trailing `/`; anything else is `CONFIG_INVALID`.
- **Slot-family addresses**: `AUTHZ_URL`, `AUTHZ_GRPC_URL`, `IAM_URL`, `IAM_GRPC_URL` hold what `$endpoint:` writes, `http://host:port` with no path (a trailing `/` is stripped); a `*_GRPC_URL` value with `http://` stripped is the gRPC target. The gRPC port is never derived from the HTTP port. A family member that does not run leaves the key absent (`present: false`).
- **Key names**: `^[A-Z][A-Z0-9_]*$`; `COMPONENT_ID`, `COMPONENT_VERSION`, `PORT`, `BRICKKIT_SERVED_MEMBERS*` and every `*_ENDPOINT` belong to the platform.
- **Secret declarations**: `secret: true` ⇔ `mount: file` ⇔ the name ends in `_FILE`. brickKit's own rules come first: `mount` is only `file`, only with `secret: true`, only on a `string`.
- **Value forms** (be-ops, gates): `$var:NAME` must be the whole value; `${NAME}` or `${NAME:-default}` (references never nest); a template may embed `${NAME}`; `file://` paths are relative to the project and stay inside it; `existingSecret` is for `secret: true` items only; `$endpoint:<scope>/<name>[@<x.y.z>][:<port name>][/<path>]` is the whole value, never for a secret (the version comes before the port, the first `/` after the name starts the path). **A secret is only ever a reference**: a literal, a template or a non-empty plaintext default for a `secret: true` item is rejected.

## Errors

| Class | When |
|---|---|
| `CONFIG_MISSING`, `CONFIG_INVALID`, `CONFIG_UNDECLARED` | at start: exit code 78 with one JSON log line naming the key (P1.2); in a shell all members' errors are collected first |
| `COMPONENT_INVALID`, `PORT_NAME_INVALID` | malformed dependency id or port name |
| `CONFIG_KEY_INVALID`, `CONFIG_KEY_RESERVED` | a key a component may not declare (gate); `CONFIG_KEY_INVALID` also for a family address read under another key |
| `SECRET_NOT_FILE`, `FILE_SUFFIX_REQUIRED`, `FILE_SUFFIX_RESERVED`, `MOUNT_INVALID`, `MOUNT_NEEDS_SECRET`, `MOUNT_NEEDS_STRING` | a secret declared another way than P2.12 (gate) |
| `FORM_INVALID`, `FORM_NOT_FOR_PLAIN`, `SECRET_NOT_REFERENCE`, `SECRET_PLAINTEXT_DEFAULT` | a value form the project does not accept (gate) |

## Decided here

For review: empty means not set for typed keys; integers are limited to ±(2^53−1); booleans are `true` / `false` / `1` / `0` only (not Go's wider `ParseBool` set); negative durations are rejected; duration lists allow no spaces; endpoint values other than `http://host:port[/]` are rejected; a secret written as a template or with a plaintext default is rejected; a secret file loses exactly one trailing newline; `_FILE` is reserved for file-delivered secrets.

## Regenerate

`python3 gen/gen_config.py`; cross-check `go run gen/xcheck_config.go .` (it also prints where Go's own helpers are broader than the protocol).
