[English](README.md) · [中文](README.zh.md)

# Fixtures

Contracts and behaviour of the fixture components the component conformance suite runs against. Nothing here is executable: each official SDK implements the widget in its own `examples/widget`, and the suite's fake peer serves the peer.

## Components

| Directory | Component | What it is |
|---|---|---|
| [widget/](widget/README.md) | `conformance/widget` 1.0.0 | the fixture every SDK implements; touches every profile; its `conformance/fixtures.yaml` is the gold sample real components copy |
| [peer/](peer/README.md) | `conformance/peer` 1.0.0 | the widget's dependency; contracts only, answered by the suite's fake peer |

## Instances

The three SDKs each build an instance of the widget with its own component ID: `conformance/widget-go`, `conformance/widget-py`, `conformance/widget-ts` (a second instance for the shell profile adds a suffix, `conformance/widget-ts2`). An instance is derived from these files mechanically:

| Changes | Stays |
|---|---|
| every occurrence of the component ID string `conformance/widget` (in `component.yaml` `metadata.id`, `assembly.yaml` `id` and `edge_routes`, `errors.yaml` `domain`, the OpenAPI `servers` URL, the paths in `fixtures.yaml`) | dotted names: permission keys `conformance.widget.*`, the resource and aggregate type `conformance.widget.widget`, the subjects `conformance.widget.*.v1`, the proto package `conformance.widget.v1` |

So the REST prefix (`/conformance/widget-go/…`), the error domain, the durable names, `be-caller` and `ce-source` differ per instance, while the contracts stay one family: like the members of a slot family, every instance publishes the same subjects. `conformance/peer` is never renamed.

## Validation

Checked when these files were written (2026-10-02): the protos build and pass `buf lint` (STANDARD) with `be/v1/limits.proto` and `google/type/date.proto`; both OpenAPI files pass `redocly lint` with no warning; `fixtures.yaml`, `errors.yaml`, `lifecycle.yaml`, `assembly.yaml` and both events files validate against `schemas/`; the samples validate against their event payload schemas; `migrations/0001_widget.sql` applies on PostgreSQL 16 and the `observe.sql` statements of `fixtures.yaml` run against it; `brickkit lint` accepts both `component.yaml` files. Re-checked 2026-10-03 with brickKit v1.3.1 after they gained `readinessCheck`, `deployment.stopGracePeriodSeconds`, port `protocol`, the `events` block and `mount: file` secrets: `brickkit lint` reports no error (only the documentation warnings of a fixture directory).
