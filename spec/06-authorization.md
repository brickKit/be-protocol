[English](06-authorization.md) · [中文](06-authorization.zh.md)

# P6 Authorization: bundle, scopes, resource contract, projection

The component side of authorization: how a component loads the permission bundle, decides a route, evaluates data scopes, filters lists with one canonical predicate, answers single-record checks, mounts the resource contract, and keeps a projection of direct grants. The provider side (bundle v2 fields, the changefeed, `Check`, `WriteTuples`) is the family contract `brickKit/contract-infra-authz`, major `authz/2`; this chapter names only what a component consumes. The meaning of a bundle (how a bundle, a verified token and a record's facts become a decision) is normative in that contract's `EVALUATION.md`, rules E1–E12, at tag `v2.0.0`; the decision vectors are canonical there (`vectors/decision/`), not in this repository. Each requirement below names the rules it relies on.

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P6.1 | MUST | Bundle: `GET {AUTHZ_URL}/authz/v2/bundle` with `If-None-Match` (ETag). Polled every 15 s; on first-load failure the retry backs off from 0.5 s doubling to 15 s; each fetch times out after 3 s; a poke on `infra.authz.changed.v1` triggers an immediate fetch; a failed fetch keeps the bundle already held (fail-static). A bundle whose `contract` is missing or does not match `authz/2.*` is refused and logged at ERROR; there is no fallback to another version. Unknown fields and unknown capability names are ignored (E1) | CP-AUTH-13 |
| P6.2 | MUST | The route decision chain, in this order: Public → allow. Verify the token ([P5](05-identity.md)) → stale check ([P5.6](05-identity.md)) → Authenticated → allow. No bundle loaded yet → `503` `AUTHZ_NOT_READY`. Delegation and ceilings (`act`, `ceil`, `dg`) → the route's key not in the union of the caller's roles' keys (intersected with each ceiling) → `403` `MISSING_PERMISSION` with `metadata.permission` = the key. Otherwise allow, with the evaluated access in the request context. Every business route declares exactly one guard: a permission key, Public or Authenticated; there is no undeclared state (E2, E4, E5) | CP-AUTH-09, CP-AUTH-10, CP-AUTH-11, CP-AUTH-12 |
| P6.3 | MUST | Levels are `own < dept < subtree < all`. For a route key K: the highest level among the caller's roles that grant K; a role that grants K without a level contributes the role's `default_level`, and without that `own`. Resource-dimension values are the union, per key, over all roles; `*` means all and is only ever granted explicitly; no value at all sees nothing. A grant's `until` (seconds since the epoch) is compared with the local clock at decision time (E3, E6, E7) | CP-SCOPE-01, CP-SCOPE-02, CP-SCOPE-03, CP-SCOPE-04, CP-SCOPE-05 |
| P6.4 | MUST | Subject set: `S(P) = {user:<sub>} ∪ {role:<r> for each role} ∪ {dept:<dept_path>} ∪ {dept_tree:<p> for p each ancestor of dept_path and itself} ∪ S(each delegator whose on-behalf delegation covers the key)`. When `dept_path` is empty, absent or not of the form `/<seg>/…/`, neither `dept` entry appears and both department arrays are empty, so nothing department-scoped matches. Only `"/"` means the whole tree; an empty string is never the root (E8) | CP-SCOPE-06 |
| P6.5 | MUST, partly INTERNAL | Lists filter with the **canonical predicate** below, a static parameterised SQL fragment with these parameter names: `@s_all`, `@s_owners[]`, `@s_dept_exact[]`, `@s_dept_prefix[]` (already suffixed with `%` and LIKE-escaped), `@s_<dim>_all`, `@s_<dim>_ids[]`, `@s_acl`, `@s_relations[]`, `@s_subjects[]`, `@s_graph_ids[]`. All values come from the evaluated access; no WHERE text is concatenated from input; no row-level security. The shape is INTERNAL; its result is tested (E6–E9) | CP-SCOPE-01, CP-SCOPE-10 |
| P6.6 | MUST | A single-record decision `Can(key, row)` yields `{visible, allowed, reason}` (E10). Visibility is decided by the resource type's `view_key`; the action by the route key K. Not visible (no rule, share or derived relation holds for `view_key`) → reads **and commands** answer `404` `NOT_FOUND`, indistinguishable from a record that does not exist. Visible but not allowed → `403`: `OUT_OF_SCOPE` when the caller holds K but this record is outside K's scope, `MISSING_PERMISSION` when the caller does not hold K. A request parameter that is itself a dimension value outside the caller's scope (`?warehouse_id=7`) also answers `403` `OUT_OF_SCOPE` | CP-SCOPE-07, CP-SCOPE-08, CP-SCOPE-09 |
| P6.7 | MUST | **List/Can consistency**: a row appears in a list for route key K if and only if `Can(K, row)` is visible (E10) | CP-SCOPE-10 |
| P6.8 | MUST (components that declare field keys) | A field key is a permission key of `type: field`. A field the caller may not read is set to `null` at the source and listed in the row's `_masked` array. Sorting, filtering or aggregating by a masked field answers `400` `SORT_FORBIDDEN`; a write to a masked field answers `403` `FIELD_FORBIDDEN` (E11) | CP-SCOPE-11 |
| P6.9 | SHOULD | Each row of a resource list carries `_access: {<action>: bool}` for the row actions the page shows; the frontend never re-derives rules | — |
| P6.10 | MUST | A component that declares `resources` in `assembly.yaml` mounts the resource contract ([`openapi/resource-authz.yaml`](../openapi/resource-authz.yaml)): `POST /{d}/{n}/_authz/check` (at most 500 checks; more answers `400` `BATCH_TOO_LARGE`), `GET /{d}/{n}/_authz/explain?key=&type=&id=` (for a record the caller cannot see, only the caller's own side of the facts), `GET`, `POST /{d}/{n}/_shares/{type}/{id}` and `DELETE /{d}/{n}/_shares/{type}/{id}/{share_id}`. A capability the provider lacks answers `501` `CAPABILITY_UNAVAILABLE` with `metadata.capability` = its name (E12). The provider's gRPC service (`WriteTuples`, `Check`, `ReadTuples`) is reached at `AUTHZ_GRPC_URL` ([P2.10](02-configuration.md)), which such a component declares | CP-SCOPE-12, CP-SCOPE-13, CP-SCOPE-14 |
| P6.11 | MUST (when capability `sharing` is true) | Consistency token: a request carrying `X-Authz-Revision: N` while the local projection's watermark is below N pulls changes once, synchronously, within 300 ms. Still behind: single reads fall back to the provider's `Check` with `at_least = N`; lists answer normally with `X-Authz-Consistency: stale`. A `_shares` write answers only after the component's own projection has reached the revision the provider returned | CP-SCOPE-15 |
| P6.12 | MUST | ACL projection, only in components that declare `resources`: tables `besdk_authz_acl` and `besdk_authz_cursor` ([ddl](../ddl/)). Pull `GET {AUTHZ_URL}/authz/v2/changes?types=<t,…>&after=<revision>&limit=500` every 5 s and immediately on a poke; `410` rebuilds from the provider's `ReadTuples` snapshot and continues from its revision. Only the component's own types and the external types it `inherits` are pulled. The projection holds direct tuples only; subject-side expansion happens at query time (P6.4) | CP-SCOPE-15 |
| P6.13 | MUST | A relation the component owns (an opportunity team, a document's temporary viewer) is written in the business transaction as an outbox event of subject `infra.authz.relation.sync.v1`, replacing the group `(type, id, relation, source)` with a monotonic version. The component never calls `WriteTuples` for it | — |
| P6.14 | INTERNAL | Decisions are never cached across requests: a remote `Check` answer is remembered for the current request at most; a caller of another component's `_authz/check` does not cache the result | — |
| P6.15 | MUST | Graph types: when the provider lacks the capability `graph`, `@s_graph_ids` is empty and the list answers with `X-Authz-Degraded: graph`. Delegation capabilities are handled at token verification ([P5.5](05-identity.md)) (E9) | — |

## Status codes for access

| Situation | Read | Command |
|---|---|---|
| no token, or an invalid one | `401` `TOKEN_INVALID` | `401` |
| token issued before the user's roles changed | `401` `TOKEN_STALE` | `401` |
| the route's permission key is missing | `403` `MISSING_PERMISSION` | `403` |
| the record does not exist | `404` `NOT_FOUND` | `404` |
| the record exists but is not visible through any rule, share or relation | `404` `NOT_FOUND`, indistinguishable | `404` |
| visible, but the action needs a key the caller lacks | — | `403` `MISSING_PERMISSION` |
| visible, the caller holds the action's key, but this record is outside that key's scope | — | `403` `OUT_OF_SCOPE` |
| visible and allowed, but the state forbids it | — | `400` with the component's reason |
| a dimension parameter outside the caller's scope | `403` `OUT_OF_SCOPE` | `403` `OUT_OF_SCOPE` |
| the bundle has not loaded yet | `503` `AUTHZ_NOT_READY` | `503` |

## The canonical predicate

```sql
AND (
      ( @s_all
        OR o.owner_id  = ANY(@s_owners)
        OR o.dept_path = ANY(@s_dept_exact)
        OR o.dept_path LIKE ANY(@s_dept_prefix) )
      -- a resource dimension is ANDed into this branch:
      --   AND (@s_wh_all OR o.warehouse_id = ANY(@s_wh_ids))
   OR ( @s_acl AND EXISTS (
          SELECT 1 FROM besdk_authz_acl a
           WHERE a.rtype = '<resource type>' AND a.rid = o.id::text
             AND a.relation = ANY(@s_relations) AND a.subject = ANY(@s_subjects)
             AND (a.expires_at IS NULL OR a.expires_at > now()) ) )
   OR o.id::text = ANY(@s_graph_ids)      -- graph types only; otherwise an empty array
)
```

| Level of the route key | `@s_all` | `@s_owners` | `@s_dept_exact` | `@s_dept_prefix` |
|---|---|---|---|---|
| `all` | `true` | `{}` | `{}` | `{}` |
| `subtree` | `false` | `{<sub>}` | `{}` | `{<dept_path>%}` |
| `dept` | `false` | `{<sub>}` | `{<dept_path>}` | `{}` |
| `own` | `false` | `{<sub>}` | `{}` | `{}` |

With no department (P6.4), `@s_dept_exact` and `@s_dept_prefix` are empty in every row of this table. A custom set of department subtrees is a value of the `org` dimension: its paths are added to `@s_dept_prefix`. A runtime MAY offer the three branches separately so a slow query becomes `UNION ALL` on the same cursor; the result MUST be identical.

## Subjects in tuples

| Form | Meaning |
|---|---|
| `user:<sub>` | one person |
| `role:<code>` | everyone holding the role |
| `dept:<path>` | everyone whose `dept_path` equals the path |
| `dept_tree:<path>` | everyone whose `dept_path` starts with the path |

## Notes

- Decisions stay local: keys, levels, values, fields and ceilings come in the bundle, direct grants in the projection, so a list is one SQL predicate and a request reaches the provider only for a graph type or a lagging consistency token.
- 404 for an invisible record stops a command from probing whether a record exists; it hides existence from the answer, not from timing.
