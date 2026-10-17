"""Chapter 08: single-object three-valued evaluation, fields and lists (P8.14-P8.18; security 01, 07)."""
from decimal import Decimal

from common import write

T, F, U = "true", "false", "unknown"

RESOURCE = {
    "type": "demo.order", "view_operation": "demo.order.read",
    "dimensions": {
        "legal_entity": {"kind": "value_set", "column": "legal_entity", "pushdown": "local_column"},
        "dept": {"kind": "org_tree", "column": "dept_path", "pushdown": "local_column"},
        "owner": {"kind": "principal", "column": "owner_id", "principal_role": "owner", "pushdown": "local_column"},
        "amount": {"kind": "amount", "column": "amount", "currency_column": "currency", "pushdown": "local_column"},
    },
    "fields": {"number": {"class": "ordinary"}, "customer": {"class": "ordinary"},
               "cost": {"class": "restricted", "read_key": "demo.order.cost"}, "note": {"class": "secret"}},
}
U1 = "0190f3a1-0000-7000-8000-0000000000a1"
U2 = "0190f3a1-0000-7000-8000-0000000000a2"
AT = "2026-10-17T02:00:00.000000Z"
ALL = {"kind": "all"}


def seg(op, fields, valid_until=None, **atoms):
    a = {d: ALL for d in RESOURCE["dimensions"]}
    a.update(atoms)
    v = {"from": "2026-01-01T00:00:00.000000Z"}
    if valid_until:
        v["until"] = valid_until
    return {"operation": op, "atoms": a, "read_fields": sorted(fields), "valid": v}


def atom(a, fact, principal):
    """One atom on one record fact. fact: {"state": "value"|"null"|"unobtained", ...}."""
    if a["kind"] == "all":
        return T
    if fact["state"] == "unobtained":
        return U
    if fact["state"] == "null":
        return F
    v = fact["value"]
    k = a["kind"]
    if k == "in":
        return T if v in a["values"] else F
    if k == "self":
        return T if v == principal else F
    if k == "tree":
        if v == "":
            return F
        for it in a["items"]:
            if v == it["path"] or (it["mode"] == "subtree" and v.startswith(it["path"] + "/")):
                return T
        return F
    if k == "interval":
        amount, currency = Decimal(v["amount"]), v["currency"]
        if currency != a["currency"]:
            return F
        if "lo" in a and (amount < Decimal(a["lo"]) or (amount == Decimal(a["lo"]) and not a["lo_closed"])):
            return F
        if "hi" in a and (amount > Decimal(a["hi"]) or (amount == Decimal(a["hi"]) and not a["hi_closed"])):
            return F
        return T
    raise ValueError(k)


def fact_of(record, dim):
    d = RESOURCE["dimensions"][dim]
    if d["kind"] == "amount":
        f = record["amount"]
        return f
    return record[d["column"]]


def segment(s, record, principal):
    if not (s["valid"]["from"] <= AT and ("until" not in s["valid"] or AT < s["valid"]["until"])):
        return F
    out = T
    for dim, a in s["atoms"].items():
        r = atom(a, fact_of(record, dim), principal)
        if r == F:
            return F
        if r == U:
            out = U
    return out


def entitled(segments, op, record, principal):
    res, fields = F, set()
    for s in segments:
        if s["operation"] != op:
            continue
        r = segment(s, record, principal)
        if r == T:
            res = T
            fields |= set(s["read_fields"])
        elif r == U and res == F:
            res = U
    return res, fields


def and3(a, b):
    if F in (a, b):
        return F
    if U in (a, b):
        return U
    return T


def evaluate(segments, record, principal, action):
    visible, fields = entitled(segments, RESOURCE["view_operation"], record, principal)
    act, _ = entitled(segments, action, record, principal)
    allowed = and3(visible, act)
    out = {"visible": visible, "fields": sorted(f for f in fields if RESOURCE["fields"][f]["class"] != "secret")
           if visible == T else [], "action": allowed}
    out["read_error"] = None if visible == T else ("NOT_FOUND" if visible == F else "AUTHORIZATION_UNPROVABLE")
    out["action_error"] = None if allowed == T else (
        "NOT_FOUND" if visible == F else "PERMISSION_DENIED" if allowed == F else "AUTHORIZATION_UNPROVABLE")
    return out


def val(v):
    return {"state": "value", "value": v}


NULL, UNOBTAINED = {"state": "null"}, {"state": "unobtained"}


def rec(rid, le, dept, owner, amount, currency="CNY"):
    return {"id": rid, "legal_entity": le, "dept_path": dept, "owner_id": owner,
            "amount": val({"amount": amount, "currency": currency}) if amount is not None else NULL,
            "number": "SO-" + rid, "customer": "C-" + rid, "cost": "1.00", "note": "secret-" + rid}


RECORDS = [
    rec("r1", val("LE1"), val("org1/org2"), val(U1), "100"),
    rec("r2", val("LE1"), val("org1/org3"), val(U2), "20000"),
    rec("r3", val("LE2"), val("org1/org2/org5"), val(U2), "500"),
    rec("r4", val("LE2"), NULL, val(U1), "50"),
    rec("r5", NULL, val("org9"), val(U2), "50"),
    rec("r6", val("LE1"), val("org1/org22"), val(U2), "10", "USD"),
    rec("r7", val("LE1"), val(""), val(U2), "10"),
]
UNKNOWN_RECORDS = [rec("r8", UNOBTAINED, val("org1/org2"), val(U2), "10"),
                   rec("r9", val("LE1"), val("org1/org2"), val(U1), "10")]
UNKNOWN_RECORDS[1]["amount"] = UNOBTAINED

READ, APPROVE = "demo.order.read", "demo.order.approve"
SCENARIOS = {
    "own-orders-in-le1": [seg(READ, ["number", "customer"], legal_entity={"kind": "in", "values": ["LE1"]},
                              owner={"kind": "self"})],
    "dept-subtree-with-cost": [seg(READ, ["number", "cost"], dept={"kind": "tree", "items": [
        {"path": "org1/org2", "mode": "subtree"}]})],
    "two-grants-keep-their-pairing": [
        seg(READ, ["number", "cost"], legal_entity={"kind": "in", "values": ["LE1"]},
            dept={"kind": "tree", "items": [{"path": "org1/org2", "mode": "exact"}]}),
        seg(READ, ["number"], legal_entity={"kind": "in", "values": ["LE2"]})],
    "approve-up-to-10000-cny": [
        seg(READ, ["number", "customer", "note"]),
        seg(APPROVE, [], amount={"kind": "interval", "currency": "CNY", "lo": "0", "lo_closed": True,
                                 "hi": "10000", "hi_closed": False})],
    "empty-in-matches-nothing": [seg(READ, ["number"], legal_entity={"kind": "in", "values": []})],
    "expired-grant": [seg(READ, ["number"], valid_until="2026-10-17T01:00:00.000000Z")],
    "approve-without-read": [seg(APPROVE, [])],
}


def segment_eval_vectors():
    cases = [{"id": "fixture", "kind": "fixture", "resource": RESOURCE, "records": RECORDS + UNKNOWN_RECORDS, "at": AT}]
    for name, segments in SCENARIOS.items():
        for principal in (U1, U2):
            per = {r["id"]: evaluate(segments, r, principal, APPROVE) for r in RECORDS + UNKNOWN_RECORDS}
            visible_ids = sorted(r["id"] for r in RECORDS if per[r["id"]]["visible"] == T)
            cases.append({"id": f"{name}-{'u1' if principal == U1 else 'u2'}", "kind": "evaluate",
                          "principal": principal, "segments": segments, "action": APPROVE,
                          "expect": {"records": per, "list": {"ids": visible_ids,
                                                              "fields": {i: per[i]["fields"] for i in visible_ids}}}})
    # P8.18: a list filter outside the grants narrows the result, no error
    segments = SCENARIOS["own-orders-in-le1"]
    cases.append({"id": "filter-outside-grant", "kind": "list", "principal": U1, "segments": segments,
                  "filter": {"legal_entity": "LE2"}, "expect": {"ids": []}})
    cases.append({"id": "filter-inside-grant", "kind": "list", "principal": U1, "segments": segments,
                  "filter": {"legal_entity": "LE1"}, "expect": {"ids": ["r1"]}})
    write("segment-eval", ["P8.14", "P8.15", "P8.16", "P8.17", "P8.18"],
          "资源 demo.order 的段（每个维度恰好一个原子）在记录上的求值。第一项 kind=fixture 给出资源定义、全部记录与求值时刻。records，其中 r8、r9 有未取得的事实（unobtained），只用于"
          "单对象求值；其余记录同时用于列表（关系型编译）。kind=evaluate：每条记录的可见性（true、false、unknown）、可读字段（secret 永不"
          "输出）、动作 demo.order.approve 的资格，与对外的错误（看不见 NOT_FOUND；可见无资格 PERMISSION_DENIED；未知 "
          "AUTHORIZATION_UNPROVABLE）；list 是可见记录的 ID 与逐行可读字段。kind=list：加上请求的筛选（按维度取值，与授权求交）后的 ID。"
          "求值时刻 " + AT + "；self 实例化为 principal。",
          cases, {"resource、records、at": "fixture 项：资源定义、记录（事实带显式存在性）与求值时刻", "principal": "请求的主体",
                  "segments": "主体的段", "expect": "逐记录结果与列表"})

