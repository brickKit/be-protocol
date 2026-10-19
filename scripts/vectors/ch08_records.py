"""Chapter 08 vectors for the security records on the wire (D76; schemas/security/): sample records that the generated
JSON Schemas accept or refuse, with the canonical bytes and digest of each accepted one."""
from ch08_canonical import canonical, digest
from common import write

DEP = "0190f3a2-7c1e-7b2a-9d4e-000000000001"
REC = "0190f3a2-7c1e-7b2a-9d4e-0000000000a1"
USER = "0190f3a2-7c1e-7b2a-9d4e-1a2b3c4d5e6f"
SRC = "0190f3a2-7c1e-7b2a-9d4e-0000000000b1"


def rev(domain, value, epoch=None, instance=None):
    r = {"domain": domain, "value": value}
    if epoch:
        r["epoch"] = epoch
    if instance:
        r["instance"] = instance
    return r


def envelope(record_type, authority, rid, revision):
    return {"record_type": record_type, "schema": "1.0", "deployment": DEP, "authority": authority, "id": rid,
            "revision": revision}


DEF_REF = {"owner_component": "demo/order", "kind": "resource", "key": "demo.order", "version": "3.0.0",
           "digest": "sha256:" + "0" * 64}

SEGMENT = {"resource_type": "demo.order", "operation": "demo.order.read",
           "atoms": {"legal_entity": {"kind": "in", "values": ["le1"]}, "owner": {"kind": "self"}},
           "read_fields": ["id", "total"], "write_fields": [], "valid": {"from": "2026-10-01T00:00:00.000000Z"},
           "source": SRC, "definition": DEF_REF}

VIEW = {**envelope("be.security.view", "infra/authz", REC, rev("authz.view.demo", "12", "1.1", "authz-inst-a")),
        "shard": "demo", "recovery_generation": rev("authz.recovery", "1"),
        "security_revisions": [rev("authz.security.legal_entity", "12", "1.1", "authz-inst-a")],
        "applicability": ["demo.order"],
        "subjects": {USER: {"segments": [SEGMENT], "accounts_disabled": False}}, "capabilities": []}

RESOURCE = {**envelope("be.security.resource_definition", "demo/order", REC, rev("demo.order.definition", "1")),
            "type": "demo.order", "view_operation": "demo.order.read",
            "dimensions": {"legal_entity": {"kind": "value_set", "column": "legal_entity", "pushdown": "local_column"},
                           "owner": {"kind": "principal", "column": "owner", "principal_role": "owner",
                                     "pushdown": "local_column"}},
            "fields": {"id": {"class": "ordinary"}, "total": {"class": "restricted", "read_key": "demo.order.read_total"},
                       "note": {"class": "secret"}}}

OPERATION = {**envelope("be.security.operation_definition", "demo/order", REC, rev("demo.order.definition", "1")),
             "key": "demo.order.approve", "resource_type": "demo.order", "purpose": "action", "risk_class": "high",
             "minimum_path": "default", "side_effects": ["business_write"], "requires_appointment": False,
             "delegable": True, "impersonation_allowed": False, "audit": "required"}

AUDIT = {"id": REC, "occurred_at": "2026-10-19T08:00:00.000000Z", "category": "business_change",
         "operation": "demo.order.approve", "outcome": "succeeded", "actor": USER,
         "target": {"type": "demo.order", "id": SRC, "revision": "4"}, "request": {"trace_id": "4bf92f3577b34da6"}}

DENIAL = {"id": REC, "occurred_at": "2026-10-19T08:00:00.000000Z", "category": "security_denial",
          "operation": "demo.order.read", "outcome": "denied", "reason": "PERMISSION_DENIED", "actor": "test/probe-go"}


def with_(record, **changes):
    r = dict(record)
    for k, v in changes.items():
        if v is None:
            r.pop(k, None)
        else:
            r[k] = v
    return r


def records_vectors():
    good = [
        ("view", "be.security.view", VIEW),
        ("resource-definition", "be.security.resource_definition", RESOURCE),
        ("operation-definition", "be.security.operation_definition", OPERATION),
        ("segment", "be.security.segment", SEGMENT),
        ("audit-record", "be.audit.record", AUDIT),
        ("audit-denial", "be.audit.record", DENIAL),
        ("resource-no-dimensions", "be.security.resource_definition", with_(RESOURCE, dimensions={})),
    ]
    bad = [
        ("view-no-applicability", "be.security.view", with_(VIEW, applicability=None), "缺必填字段"),
        ("view-with-digest", "be.security.view", with_(VIEW, digest="sha256:" + "1" * 64),
         "线上的记录不带自己的摘要（随信封传）"),
        ("view-unknown-field", "be.security.view", with_(VIEW, owner="x"), "未定义的字段（扩展只能放进 ext）"),
        ("resource-no-dimensions-key", "be.security.resource_definition", with_(RESOURCE, dimensions=None),
         "没有维度要写 {}，不能缺省"),
        ("authority-as-key", "be.security.resource_definition", with_(RESOURCE, authority="demo.order"),
         "authority 是组件 ID，不是 Key"),
        ("component-underscore", "be.security.resource_definition", with_(RESOURCE, authority="demo/order_x"),
         "组件 ID 不含下划线"),
        ("key-uppercase", "be.security.operation_definition", with_(OPERATION, key="demo.Order.approve"),
         "Key 只用小写"),
        ("enum-unknown", "be.security.operation_definition", with_(OPERATION, risk_class="medium"), "未知的枚举值"),
        ("id-not-v7", "be.security.segment", with_(SEGMENT, source="0190f3a2-7c1e-4b2a-9d4e-0000000000b1"),
         "Id 是 UUIDv7"),
        ("instant-precision", "be.audit.record", with_(AUDIT, occurred_at="2026-10-19T08:00:00Z"),
         "时刻固定 6 位小数"),
        ("float", "be.security.segment",
         with_(SEGMENT, atoms={"legal_entity": {"kind": "all"}, "owner": {"kind": "related", "relation_type": "team",
                                                                           "anchor": "subject", "max_depth": 1.5}}),
         "不出现浮点数"),
        ("atom-unknown-kind", "be.security.segment",
         with_(SEGMENT, atoms={"legal_entity": {"kind": "any"}, "owner": {"kind": "self"}}), "未知的原子种类"),
        ("audit-outcome", "be.audit.record", with_(AUDIT, outcome="ok"), "未知的结果"),
    ]
    cases = []
    for cid, rt, rec in good:
        cases.append({"id": cid, "record_type": rt, "record": rec, "valid": True,
                      "canonical": canonical(rec).decode(), "digest": digest(rt, 1, rec)})
    for cid, rt, rec, why in bad:
        cases.append({"id": cid, "record_type": rt, "record": rec, "valid": False, "why": why})
    write("security-records", ["P8.8", "P8.11", "P8.20"],
          "线上的安全记录与审计记录（D76：以规范 JSON 字节放在信封的 bytes 字段里）对 schemas/security/ 下生成的 JSON Schema"
          "（装配项目安全 09a 与本章的字段表生成）的校验。valid=true 的记录 schema 接受，并给出规范字节（canonical）与摘要"
          "（记录类型取 record_type，主版本 1）；valid=false 的记录 schema 拒绝，why 说明原因。schema 只查结构与类型；"
          "约束一列里的条件规则（例如 restricted 字段必有 read_key）由代码检查，不在这里。",
          cases, {"record_type": "记录类型，也是 schema 文件名（<record_type>.schema.json）",
                  "record": "记录内容（不含 digest）", "valid": "schema 是否接受",
                  "canonical、digest": "valid=true：规范字节与摘要"})
