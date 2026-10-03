[English](06-authorization.md) · [中文](06-authorization.zh.md)

# P6 授权：bundle、范围、资源契约、投影

授权的组件一侧：组件怎么加载权限 bundle、怎么判定一个路由、怎么求值数据范围、怎么用一个规范谓词过滤列表、怎么回答单条记录的检查、怎么挂出资源契约，以及怎么维护一份直接授予的投影。provider 一侧（bundle v2 的字段、变更流、`Check`、`WriteTuples`）是族契约 `brickKit/contract-infra-authz`，major `authz/2`；本章只写组件消费的那部分。bundle 的含义（一份 bundle、一个验证过的 token 和一条记录的事实怎么变成一个判定）以该契约 tag `v2.0.0` 的 `EVALUATION.md` 规则 E1–E12 为规范；判定向量以那里（`vectors/decision/`）为准，不在本仓库。下面每条要求都写明它依赖哪些规则。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P6.1 | MUST | bundle：`GET {AUTHZ_URL}/authz/v2/bundle`，带 `If-None-Match`（ETag）。每 15 s 轮询一次；首次加载失败时，重试按 0.5 s 起步、翻倍、上限 15 s 退避；每次拉取 3 s 超时；收到 `infra.authz.changed.v1` 的 poke 立刻拉一次；拉取失败沿用已有的 bundle（fail-static）。`contract` 缺失或不匹配 `authz/2.*` 的 bundle 被拒绝，并记 ERROR 日志；不回退到别的版本。不认识的字段和不认识的能力名忽略（E1） | CP-AUTH-13 |
| P6.2 | MUST | 路由判定链，按这个顺序，第一个作出判定的说了算：Public → 放行。验证 token（[P5.1](05-identity.zh.md)–P5.3、P5.9）→ `401` `TOKEN_INVALID`。还没加载过 bundle → `503` `AUTHZ_NOT_READY`，凡不是 Public 的路由都这样，Authenticated 路由也算（[P1.5](01-process-and-lifecycle.zh.md)）。token 过期或授权已撤销（[P5.6](05-identity.zh.md)）→ `401` `TOKEN_STALE`。沿 `act` 链检查代理能力（[P5.5](05-identity.zh.md)）→ `401` `UNSUPPORTED_DELEGATION`。Authenticated → 放行。天花板（`ceil`）和代为行事的委托 → 路由的键不在调用方各角色键的并集里（与每个天花板求交）→ `403` `MISSING_PERMISSION`，`metadata.permission` = 该键。否则放行，并把求值后的访问权放进请求上下文。每个业务路由恰好声明一个守卫：一个权限键、Public 或 Authenticated，写在它 OpenAPI operation 的 `x-be-permission` 上（[P3.16](03-http-surface.zh.md)）；没声明的守卫按失败即关闭处理（E2, E4, E5） | CP-AUTH-09, CP-AUTH-10, CP-AUTH-11, CP-AUTH-12 |
| P6.3 | MUST | 档位是 `own < dept < subtree < all`。对路由键 K：取调用方所有授予 K 的角色里最高的档位；授予了 K 但没写档位的角色，贡献该角色的 `default_level`，没有就是 `own`。资源维度的取值，按键取所有角色的并集；`*` 表示全部，只能显式授予；一个取值都没有就什么都看不到。授予的 `until`（自 epoch 起的秒数）在判定时与本地时钟比较（E3, E6, E7） | CP-SCOPE-01, CP-SCOPE-02, CP-SCOPE-03, CP-SCOPE-04, CP-SCOPE-05 |
| P6.4 | MUST | 主体集合：`S(P) = {user:<sub>} ∪ {role:<r> for each role} ∪ {dept:<dept_path>} ∪ {dept_tree:<p> for p each ancestor of dept_path and itself} ∪ S(each delegator whose on-behalf delegation covers the key)`。`dept_path` 为空、缺失或不是 `/<seg>/…/` 形式时，两个 dept 项都不出现，两个部门数组都为空，于是任何按部门限定的东西都匹配不到。只有 `"/"` 表示整棵树；空串永远不是根（E8） | CP-SCOPE-06 |
| P6.5 | MUST，部分 INTERNAL | 列表用下面的**规范谓词**过滤，它是一段静态参数化 SQL 片段，参数名为：`@s_all`、`@s_owners[]`、`@s_dept_exact[]`、`@s_dept_prefix[]`（已经补好 `%` 并做了 LIKE 转义）、`@s_<dim>_all`、`@s_<dim>_ids[]`、`@s_acl`、`@s_relations[]`、`@s_subjects[]`、`@s_graph_ids[]`。所有取值都来自求值后的访问权；不从输入拼接任何 WHERE 文本；不用行级安全。形状是 INTERNAL；它的结果被测试（E6–E9） | CP-SCOPE-01, CP-SCOPE-10 |
| P6.6 | MUST | 单条记录判定 `Can(key, row)` 给出 `{visible, allowed, reason}`（E10）。看不看得见由资源类型的 `view_key` 决定；动作由路由键 K 决定。看不见（对 `view_key` 而言，规则、分享、派生关系都不成立）→ 读**和命令**都答 `404` `NOT_FOUND`，与记录不存在无法区分。看得见但不被允许 → `403`：调用方持有 K、但这条记录不在 K 的范围内时是 `OUT_OF_SCOPE`，调用方不持有 K 时是 `MISSING_PERMISSION`。请求参数本身就是一个维度取值、且不在调用方范围内时（`?warehouse_id=7`），也答 `403` `OUT_OF_SCOPE` | CP-SCOPE-07, CP-SCOPE-08, CP-SCOPE-09 |
| P6.7 | MUST | **List 与 Can 一致**：一行出现在路由键 K 的列表里，当且仅当 `Can(K, row)` 为 visible（E10） | CP-SCOPE-10 |
| P6.8 | MUST（声明了字段键的组件） | 字段键是 `type: field` 的权限键。调用方不能读的字段在源头置为 `null`，并列进该行的 `_masked` 数组。按掩码字段排序、过滤或聚合，答 `400` `SORT_FORBIDDEN`；写掩码字段，答 `403` `FIELD_FORBIDDEN`（E11） | CP-SCOPE-11 |
| P6.9 | SHOULD | 资源列表的每一行带 `_access: {<action>: bool}`，覆盖页面上显示的行操作；前端从不自己重新推导规则 | — |
| P6.10 | MUST | 在 `assembly.yaml` 里声明了 `resources` 的组件挂出资源契约（[`openapi/resource-authz.yaml`](../openapi/resource-authz.yaml)）：`POST /{d}/{n}/_authz/check`（最多 500 条检查；超过答 `400` `BATCH_TOO_LARGE`）、`GET /{d}/{n}/_authz/explain?key=&type=&id=`（对调用方看不见的记录，只给调用方本人一侧的事实）、`GET`、`POST /{d}/{n}/_shares/{type}/{id}` 和 `DELETE /{d}/{n}/_shares/{type}/{id}/{share_id}`。provider 缺的能力答 `501` `CAPABILITY_UNAVAILABLE`，`metadata.capability` = 能力名（E12）。provider 的 gRPC 服务（`WriteTuples`、`Check`、`ReadTuples`）经 `AUTHZ_GRPC_URL` 访问（[P2.10](02-configuration.zh.md)），这样的组件要声明这个键 | CP-SCOPE-12, CP-SCOPE-13, CP-SCOPE-14 |
| P6.11 | MUST（能力 `sharing` 为真时） | 一致性令牌：请求带了 `X-Authz-Revision: N`，而本地投影的水位低于 N，就同步拉一次变更，限时 300 ms。仍然落后：单条读回落到 provider 的 `Check`，带 `at_least = N`；列表照常回答，带 `X-Authz-Consistency: stale`。`_shares` 写入要等组件自己的投影追上 provider 返回的 revision 后才响应 | CP-SCOPE-15 |
| P6.12 | MUST | ACL 投影，只在声明了 `resources` 的组件里有：表 `besdk_authz_acl` 和 `besdk_authz_cursor`（[ddl](../ddl/)）。每 5 s、以及收到 poke 时立刻，拉取 `GET {AUTHZ_URL}/authz/v2/changes?types=<t,…>&after=<revision>&limit=500`；遇到 `410` 就用 provider 的 `ReadTuples` 快照重建，并从快照的 revision 继续。只拉组件自己的类型，以及它 `inherits` 的外部类型。投影里只有直接元组；主体一侧的展开在查询时进行（P6.4） | CP-SCOPE-15 |
| P6.13 | MUST | 组件主责的关系（商机团队、单据的临时查看人）在业务事务里写成一条 subject 为 `infra.authz.relation.sync.v1` 的 outbox 事件，以单调递增的版本替换 `(type, id, relation, source)` 这一组。组件从不为此调用 `WriteTuples` | — |
| P6.14 | INTERNAL | 判定结果从不跨请求缓存：远程 `Check` 的回答最多在本次请求内记住；调用别的组件 `_authz/check` 的一方不缓存结果 | — |
| P6.15 | MUST | 图类型：provider 缺 `graph` 能力时，`@s_graph_ids` 为空，列表回答时带 `X-Authz-Degraded: graph`。委托相关的能力在验证 token 时处理（[P5.5](05-identity.zh.md)）（E9） | — |

## 访问相关的状态码

| 情形 | 读 | 命令 |
|---|---|---|
| 没有 token，或 token 无效 | `401` `TOKEN_INVALID` | `401` |
| token 签发于用户角色变更之前 | `401` `TOKEN_STALE` | `401` |
| 缺路由的权限键 | `403` `MISSING_PERMISSION` | `403` |
| 记录不存在 | `404` `NOT_FOUND` | `404` |
| 记录存在，但经任何规则、分享或关系都看不见 | `404` `NOT_FOUND`，无法区分 | `404` |
| 看得见，但动作需要一个调用方没有的键 | — | `403` `MISSING_PERMISSION` |
| 看得见，调用方持有动作的键，但这条记录不在该键的范围内 | — | `403` `OUT_OF_SCOPE` |
| 看得见且被允许，但状态不允许 | — | `400`，带组件自己的 reason |
| 维度参数不在调用方范围内 | `403` `OUT_OF_SCOPE` | `403` `OUT_OF_SCOPE` |
| bundle 还没加载 | `503` `AUTHZ_NOT_READY` | `503` |

## 规范谓词

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

| 路由键的档位 | `@s_all` | `@s_owners` | `@s_dept_exact` | `@s_dept_prefix` |
|---|---|---|---|---|
| `all` | `true` | `{}` | `{}` | `{}` |
| `subtree` | `false` | `{<sub>}` | `{}` | `{<dept_path>%}` |
| `dept` | `false` | `{<sub>}` | `{<dept_path>}` | `{}` |
| `own` | `false` | `{<sub>}` | `{}` | `{}` |

没有部门时（P6.4），这张表每一行的 `@s_dept_exact` 和 `@s_dept_prefix` 都为空。自定义的一组部门子树是 `org` 维度的一个取值：它的路径加进 `@s_dept_prefix`。运行时可以把三个分支分开提供，让慢查询变成同一个游标上的 `UNION ALL`；结果必须完全相同。

## 元组里的主体

| 形式 | 含义 |
|---|---|
| `user:<sub>` | 一个人 |
| `role:<code>` | 持有该角色的所有人 |
| `dept:<path>` | `dept_path` 等于该路径的所有人 |
| `dept_tree:<path>` | `dept_path` 以该路径开头的所有人 |

## 说明

- 判定留在本地：键、档位、取值、字段和天花板随 bundle 而来，直接授予在投影里，所以一个列表就是一个 SQL 谓词；只有图类型或落后的一致性令牌，请求才会去找 provider。
- 对看不见的记录答 404，是为了不让命令探测出一条记录是否存在；它在回答里隐藏了存在性，没有在耗时上隐藏。
