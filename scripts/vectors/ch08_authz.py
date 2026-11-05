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


def shown(fields, visible):
    """The readable fields as output: none unless visible, never a secret one."""
    return sorted(f for f in fields if RESOURCE["fields"][f]["class"] != "secret") if visible == T else []


def evaluate(segments, record, principal, action):
    visible, fields = entitled(segments, RESOURCE["view_operation"], record, principal)
    act, action_fields = entitled(segments, action, record, principal)
    allowed = and3(visible, act)
    # security 01's Readable(C,K,r,f): the operation's own true segments, only on a visible record
    out = {"visible": visible, "fields": shown(fields, visible), "action": allowed,
           "action_fields": shown(action_fields, visible)}
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
    rec("r10", val("LE2"), val("org1/org2"), val(U1), "75"),
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
    # AE02: two read scopes, only one of them approvable
    "approve-in-one-scope-only": [
        seg(READ, ["number"], legal_entity={"kind": "in", "values": ["LE1"]}),
        seg(READ, ["number"], legal_entity={"kind": "in", "values": ["LE2"]}),
        seg(APPROVE, ["number"], legal_entity={"kind": "in", "values": ["LE1"]})],
    # AE03: LE1 up to 100 (closed), LE2 up to 50 (open): r10 (LE2, 75) cannot borrow LE1's limit; the ends are
    # checked as declared (r1 at 100 closed: yes; r4 at 50 open: no)
    "limits-are-not-borrowed": [
        seg(READ, ["number"]),
        seg(APPROVE, [], legal_entity={"kind": "in", "values": ["LE1"]},
            amount={"kind": "interval", "currency": "CNY", "hi": "100", "hi_closed": True}),
        seg(APPROVE, [], legal_entity={"kind": "in", "values": ["LE2"]},
            amount={"kind": "interval", "currency": "CNY", "hi": "50", "hi_closed": False})],
    # AE07, FX09: two segments over the same row read different fields; another row hit by one takes only its fields
    "overlapping-segments-union-their-fields": [
        seg(READ, ["number", "cost"], legal_entity={"kind": "in", "values": ["LE1"]}),
        seg(READ, ["number", "customer"], dept={"kind": "tree", "items": [{"path": "org1/org2", "mode": "subtree"}]})],
    # AE08: an export operation outputs its own segments' fields, not the page's
    "export-uses-its-own-fields": [
        seg(READ, ["number", "customer", "cost"]),
        seg(APPROVE, ["number"], legal_entity={"kind": "in", "values": ["LE1"]})],
    # AE10, FX02: owner OR dept, both branches keeping the legal entity
    "owner-or-dept-keeps-the-legal-entity": [
        seg(READ, ["number"], legal_entity={"kind": "in", "values": ["LE1"]}, owner={"kind": "self"}),
        seg(READ, ["number"], legal_entity={"kind": "in", "values": ["LE1"]},
            dept={"kind": "tree", "items": [{"path": "org1/org2", "mode": "subtree"}]})],
    # FX08: one segment unknown on a record, another proven: allowed with the proven segment's fields only
    "one-unknown-one-proven": [
        seg(READ, ["number", "cost"], legal_entity={"kind": "in", "values": ["LE1"]}),
        seg(READ, ["number"], dept={"kind": "tree", "items": [{"path": "org1/org2", "mode": "exact"}]})],
    # an amount limit on reading (the amount dimension's list filters)
    "read-up-to-100-cny": [seg(READ, ["number"], amount={"kind": "interval", "currency": "CNY", "hi": "100",
                                                          "hi_closed": True})],
    # FX03: an empty interval matches nothing
    "empty-interval-matches-nothing": [
        seg(READ, ["number"], amount={"kind": "interval", "currency": "CNY", "lo": "100", "lo_closed": True,
                                      "hi": "100", "hi_closed": False})],
}

# Segments a component refuses against its own resource definition (P8.14; security 09a's EN08-EN10).
CHECKS = [
    ("well-formed", seg(READ, ["number"], amount={"kind": "interval", "currency": "CNY", "hi": "10", "hi_closed": True}),
     True, "合格"),
    ("missing-dimension", {**seg(READ, ["number"]), "atoms": {d: ALL for d in ("legal_entity", "dept", "owner")}},
     False, "少一个维度：不能当作 all"),
    ("extra-dimension", {**seg(READ, ["number"]), "atoms": {**seg(READ, [])["atoms"], "warehouse": ALL}},
     False, "多一个未定义的维度"),
    ("renamed-dimension", {**seg(READ, ["number"]), "atoms": {**{d: ALL for d in ("legal_entity", "dept", "owner")},
                                                              "warehouse": ALL}},
     False, "原子数对，但缺 amount、多一个未定义的 warehouse"),
    ("write-not-readable", {**seg(READ, ["number"]), "write_fields": ["customer"]}, False, "写字段不在读字段里"),
    ("interval-without-closed", seg(READ, ["number"], amount={"kind": "interval", "currency": "CNY", "hi": "10"}),
     False, "区间给了 hi 不给 hi_closed"),
    ("interval-without-ends", seg(READ, ["number"], amount={"kind": "interval", "currency": "CNY"}), False,
     "区间两端都缺"),
    ("tree-on-a-value-set", seg(READ, ["number"], legal_entity={"kind": "tree", "items": [
        {"path": "LE1", "mode": "exact"}]}), False, "组织树原子用在值集合维度上"),
    ("self-on-a-value-set", seg(READ, ["number"], legal_entity={"kind": "self"}), False, "self 用在不是主体的维度上"),
    ("unknown-kind", seg(READ, ["number"], legal_entity={"kind": "any"}), False, "不认识的原子种类"),
]

# The masked output (P8.31): an object as the component built it, the readable fields, the output.
MASKS = [
    ("partly-readable", {"number": "SO-r1", "customer": None, "cost": "1.00", "note": "secret-r1", "extra": "x"},
     ["customer", "number"], {"number": "SO-r1", "customer": None, "cost": None, "_masked": ["cost"]}),
    ("all-readable", {"number": "SO-r1", "customer": None, "cost": "1.00"}, ["cost", "customer", "number"],
     {"number": "SO-r1", "customer": None, "cost": "1.00"}),
    ("nothing-readable", {"number": "SO-r1", "customer": "C-r1", "cost": "1.00"}, [],
     {"number": None, "customer": None, "cost": None, "_masked": ["cost", "customer", "number"]}),
]


def segment_eval_vectors():
    cases = [{"id": "fixture", "kind": "fixture", "resource": RESOURCE, "records": RECORDS + UNKNOWN_RECORDS, "at": AT}]
    for name, segments in SCENARIOS.items():
        for principal in (U1, U2):
            per = {r["id"]: evaluate(segments, r, principal, APPROVE) for r in RECORDS + UNKNOWN_RECORDS}
            visible_ids = sorted(r["id"] for r in RECORDS if per[r["id"]]["visible"] == T)
            allowed_ids = sorted(r["id"] for r in RECORDS if per[r["id"]]["action"] == T)
            cases.append({"id": f"{name}-{'u1' if principal == U1 else 'u2'}", "kind": "evaluate",
                          "principal": principal, "segments": segments, "action": APPROVE,
                          "expect": {"records": per,
                                     "list": {"ids": visible_ids, "fields": {i: per[i]["fields"] for i in visible_ids}},
                                     "action_list": {"ids": allowed_ids,
                                                     "fields": {i: per[i]["action_fields"] for i in allowed_ids}}}})
    # P8.18: a list filter outside the grants narrows the result, no error; one pair per dimension (the filter is
    # column = value)
    filters = [
        ("filter-outside-grant", "own-orders-in-le1", U1, {"legal_entity": "LE2"}),
        ("filter-inside-grant", "own-orders-in-le1", U1, {"legal_entity": "LE1"}),
        ("filter-outside-subtree", "dept-subtree-with-cost", U1, {"dept_path": "org1/org3"}),
        ("filter-inside-subtree", "dept-subtree-with-cost", U1, {"dept_path": "org1/org2/org5"}),
        ("filter-another-owner", "own-orders-in-le1", U1, {"owner_id": U2}),
        ("filter-own", "own-orders-in-le1", U1, {"owner_id": U1}),
        ("filter-amount-outside-limit", "read-up-to-100-cny", U1, {"amount": "20000"}),
        ("filter-amount-inside-limit", "read-up-to-100-cny", U1, {"amount": "50"}),
        ("filter-another-currency", "read-up-to-100-cny", U1, {"currency": "USD"}),
    ]
    for cid, scenario, principal, flt in filters:
        segments = SCENARIOS[scenario]
        col_dim = {d["column"]: n for n, d in RESOURCE["dimensions"].items()}
        ids = []
        for r in RECORDS:
            if evaluate(segments, r, principal, APPROVE)["visible"] != T:
                continue
            ok = True
            for col, v in flt.items():
                if col in ("currency", "amount"):
                    f = r["amount"]
                    ok = ok and f["state"] == "value" and (f["value"]["currency"] == v if col == "currency"
                                                           else Decimal(f["value"]["amount"]) == Decimal(v))
                else:
                    f = r[col]
                    ok = ok and f["state"] == "value" and f["value"] == v
                    assert col in col_dim
            if ok:
                ids.append(r["id"])
        cases.append({"id": cid, "kind": "list", "principal": principal, "segments": segments, "filter": flt,
                      "expect": {"ids": sorted(ids)}})
    for cid, segment, valid, why in CHECKS:
        cases.append({"id": "check-" + cid, "kind": "check", "segment": segment, "valid": valid, "why": why})
    for cid, obj, readable, out in MASKS:
        cases.append({"id": "mask-" + cid, "kind": "mask", "object": obj, "readable": readable, "expect": out})
    write("segment-eval", ["P8.14", "P8.15", "P8.16", "P8.17", "P8.18", "P8.31"],
          "资源 demo.order 的段（每个维度恰好一个原子）在记录上的求值。第一项 kind=fixture 给出资源定义、全部记录与求值时刻。records，其中 r8、r9 有未取得的事实（unobtained），只用于"
          "单对象求值；其余记录同时用于列表（关系型编译）。kind=evaluate：每条记录的可见性（true、false、unknown）、可读字段（secret 永不"
          "输出）、动作 demo.order.approve 的资格，与对外的错误（看不见 NOT_FOUND；可见无资格 PERMISSION_DENIED；未知 "
          "AUTHORIZATION_UNPROVABLE）；fields 是读取操作的可读字段，action_fields 是对动作自己的段可读的字段（安全 01 的 "
          "Readable(C,K,r,f)）；list 是可见记录的 ID 与逐行可读字段，action_list 是可执行动作的记录（列表按动作编译）与逐行的 "
          "action_fields。kind=list：加上请求的筛选（列 = 值，与授权求交）后的 ID。kind=check：段对 fixture 的资源定义是否合格"
          "（不合格的不参与求值，P8.14）。kind=mask：组件建好的输出对象按可读字段掩码后的样子（P8.31）。"
          "求值时刻 " + AT + "；self 实例化为 principal。",
          cases, {"resource、records、at": "fixture 项：资源定义、记录（事实带显式存在性）与求值时刻", "principal": "请求的主体",
                  "segments": "主体的段", "expect": "逐记录结果与列表"})

