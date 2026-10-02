[English](20-self-description-and-versioning.md) · [中文](20-self-description-and-versioning.zh.md)

# P20 Self-description and protocol version

How a component says which protocol version it implements, what it is built with and what it serves, and how the protocol itself changes.

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P20.1 | — (rule for this repository) | The protocol version is `MAJOR.MINOR`. A minor version adds only **optional** surface: a new capability bit, a new optional endpoint, field, header, key or reason; it never changes the meaning of what an earlier version of the same major defines. A behaviour that becomes required appears only in a new major | — |
| P20.2 | MUST | A component declares `protocol: "<MAJOR.MINOR>"` in `assembly.yaml` ([schema](../schemas/assembly-protocol.schema.json)) and is tested against that version's case set. The suite keeps one case set per minor; an older component is always tested against the version it declares. A component not written with an official SDK also declares `language: <name>` | CP-CORE-11 |
| P20.3 | MUST | An SDK states the protocol version it implements in its README and in `/_be/info` | CP-CORE-11 |
| P20.4 | MUST | `GET /_be/info` on the main port: never routed by the edge, no authentication, no secret values. Its body matches [`info.schema.json`](../schemas/info.schema.json) and agrees with the image's manifests (ID, version, ports) | CP-CORE-11 |

## `/_be/info`

```json
{
  "component_id": "erp/sales",
  "component_version": "3.0.0",
  "protocol": "1.0",
  "sdk": { "name": "be-sdk-go", "version": "0.6.0" },
  "language": { "name": "go", "version": "1.25.11" },
  "profiles": ["core", "auth", "scope", "grpc", "outbound", "events-pub", "events-sub", "idempotency", "db", "jobs", "lifecycle"],
  "ports": { "http": 8085, "grpc": 9095 },
  "migrations": { "component": "0001", "platform": 1 },
  "members": null
}
```

| Field | Meaning |
|---|---|
| `component_id`, `component_version` | equal to `COMPONENT_ID` and `COMPONENT_VERSION` |
| `protocol` | the version implemented, equal to `assembly.yaml`'s `protocol` |
| `sdk` | the official SDK and its version; `null` for a component without one |
| `language` | the language and its runtime version |
| `profiles` | the profiles the component claims; the suite compares them with those it selects from the manifests |
| `ports` | `http` = the main port, plus each extra port by name |
| `migrations.component` | the newest component migration applied in the image; `migrations.platform` the platform migration version (`besdk_platform_version`) |
| `tzdata` | optional: the version of the IANA time-zone data the runtime embeds, e.g. `2026c` ([P11.7](11-migrations-and-data-shapes.md)) |
| `degraded` | optional: what runs in a degraded mode decided at start, e.g. `calendar` when `mdm/org` is not installed ([P11.9](11-migrations-and-data-shapes.md)); absent or empty when nothing is degraded |
| `members` | `null` for a component; on a shell an array of member objects of the same shape without `members` |

## Notes

- The suite reads `/_be/info` first and checks it against the container and the manifests before running any profile.
- Requirement and case IDs are stable across versions ([00-reading-the-spec](00-reading-the-spec.md#identifiers)).
