[English](README.md) · [中文](README.zh.md)

# Fixture: peer

`conformance/peer` is the dependency of the widget fixture. It has contracts and no implementation: the component conformance suite's fake peer answers its gRPC methods from `contracts/conformance/peer/v1/peer.proto` and its one HTTP operation from `contracts/peer.openapi.yaml`, with the canned answers in the widget's `conformance/fixtures.yaml`, and it can hang, slow down or fail any of them. It records what it receives (metadata, deadlines, connections, headers), which is how the outbound cases observe the widget.

## Surface

| Surface | Operation | Used by the widget for |
|---|---|---|
| gRPC | `Reserve` (`IDEMPOTENT`) | approval step 2 |
| gRPC | `GetReservationStatus` (`NO_SIDE_EFFECTS`) | the reconciler; `slow?via=peer` |
| gRPC | `BatchGetOwners`, `ListOwners` (`NO_SIDE_EFFECTS`) | the owner snapshot (read-through, backfill) |
| gRPC | `Notify` (`IDEMPOTENT`) | the queued job `widget.notify` |
| HTTP | `GET /conformance/peer/owners/{owner_id}` | `GET /conformance/widget/widgets/{id}/owner` (UserHTTP) |
| events | `conformance.owner.updated.v1`, `conformance.reservation.expired.v1` | published by the suite on the peer's behalf |
| errors | `QUOTA_EXCEEDED` (`FAILED_PRECONDITION`) | relayed by the widget with domain `conformance/peer` |
