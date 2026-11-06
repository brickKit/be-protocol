"""Chapter 15: hot and cold data. The canonical row and the unit's digest (P15.8-P15.10), the object key and the manifest
(P15.15, P15.16), and the planning function (P15.37)."""
import base64
import hashlib
import struct
import unicodedata
from datetime import date, datetime, timedelta, timezone

from ch08_canonical import Refused, canonical, digest, norm_decimal, norm_instant
from common import write

INTEGER = {"int2", "int4", "int8"}


def canon_value(typ, v):
    """One column's value in a canonical row (P15.8); None is not written."""
    if typ == "text":
        return unicodedata.normalize("NFC", v)
    if typ in INTEGER:
        if isinstance(v, bool) or not isinstance(v, (int, str)):
            raise Refused("integer")
        s = norm_decimal(str(v))
        if "." in s:
            raise Refused("integer")
        return s
    if typ == "numeric":
        return norm_decimal(str(v))
    if typ == "bool":
        if not isinstance(v, bool):
            raise Refused("bool")
        return v
    if typ == "uuid":
        s = v.lower()
        if len(s) != 36 or s.count("-") != 4:
            raise Refused("uuid")
        return s
    if typ == "timestamptz":
        return norm_instant(v)
    if typ == "date":
        return date.fromisoformat(v).isoformat()
    if typ == "jsonb":
        return v  # the source's text, as it came
    if typ == "bytea":
        return base64.b64encode(bytes.fromhex(v)).decode()
    raise Refused("type")


def canon_row(columns, row):
    """columns: {name: type}; row: {name: value or None} -> the canonical row's bytes."""
    return canonical({k: canon_value(columns[k], v) for k, v in row.items() if v is not None})


def canon_pk(columns, pk, row):
    return canonical([canon_value(columns[k], row[k]) for k in pk])


def table_hash(columns, pk, rows):
    h = hashlib.sha256()
    for _, b in sorted((canon_pk(columns, pk, r), canon_row(columns, r)) for r in rows):
        h.update(struct.pack(">Q", len(b)) + b)
    return h.hexdigest()


def unit_digest(cls, schema_version, tables):
    """tables: [{name, columns, pk, rows}] -> the unit's digest (P15.9)."""
    entries = sorted(({"name": t["name"], "rows": str(len(t["rows"])),
                       "sha256": table_hash(t["columns"], t["pk"], t["rows"])} for t in tables),
                     key=lambda e: e["name"])
    return digest("be.tier.unit", 1, {"class": cls, "schema_version": schema_version, "tables": entries})


ORDERS = {"id": "uuid", "legal_entity": "uuid", "code": "text", "note": "text", "total": "numeric",
          "lines": "int4", "closed_at": "timestamptz", "day": "date", "paid": "bool", "attrs": "jsonb", "blob": "bytea"}
LINES = {"order_id": "uuid", "line": "int4", "qty": "int8", "price": "numeric"}
O1, O2 = "0190f3a1-0000-7000-8000-0000000000a1", "0190F3A1-0000-7000-8000-0000000000A2"
LE = "0190f3a1-0000-7000-8000-00000000e001"


def digest_vectors():
    cases = []

    def row_case(cid, description, columns, row, want=None, refused=False):
        if refused:
            try:
                canon_row(columns, row)
            except Refused:
                cases.append({"id": cid, "description": description, "input": {"columns": columns, "row": row},
                              "expected": {"refused": True}})
                return
            raise AssertionError(cid)
        got = canon_row(columns, row).decode()
        assert want is None or got == want, (cid, got)
        cases.append({"id": cid, "description": description, "input": {"columns": columns, "row": row},
                      "expected": {"canonical_row": got}})

    row_case("all-types", "every type once", ORDERS,
             {"id": O1, "legal_entity": LE, "code": "SO-1", "note": "café", "total": "1250.50", "lines": 3,
              "closed_at": "2026-03-01T08:00:00.5+01:00", "day": "2026-03-01", "paid": True,
              "attrs": '{"channel": "web"}', "blob": "00ff10"})
    row_case("null-is-not-written", "a null column is left out; an empty string is kept", {"code": "text", "note": "text"},
             {"code": "", "note": None}, '{"code":""}')
    row_case("nfc", "text is NFC: e and a combining acute become é", {"note": "text"}, {"note": "café"},
             '{"note":"café"}')
    row_case("big-integer", "an 8-byte integer past 2^53 is a decimal string", {"qty": "int8"},
             {"qty": 9007199254740993}, '{"qty":"9007199254740993"}')
    row_case("numeric-normalized", "trailing zeros and a negative zero", {"a": "numeric", "b": "numeric"},
             {"a": "1.50", "b": "-0.000"}, '{"a":"1.5","b":"0"}')
    row_case("instant-utc", "an instant with an offset becomes UTC microseconds", {"t": "timestamptz"},
             {"t": "2026-03-01T08:00:00.5+01:00"}, '{"t":"2026-03-01T07:00:00.500000Z"}')
    row_case("uuid-lower", "a UUID is lower case", {"id": "uuid"}, {"id": O2},
             '{"id":"0190f3a1-0000-7000-8000-0000000000a2"}')
    row_case("numeric-nan-refused", "NaN is not a decimal", {"a": "numeric"}, {"a": "NaN"}, refused=True)
    row_case("integer-fraction-refused", "an integer column with a fraction", {"q": "int4"}, {"q": "1.5"}, refused=True)

    pk_cols = {"order_id": "uuid", "line": "int4"}
    got = canon_pk(pk_cols, ["order_id", "line"], {"order_id": O1, "line": 12}).decode()
    cases.append({"id": "composite-pk", "description": "a primary key is the array of its columns' values, in key order",
                  "input": {"columns": pk_cols, "pk": ["order_id", "line"], "row": {"order_id": O1, "line": 12}},
                  "expected": {"canonical_pk": got}})

    lines = [{"order_id": O1, "line": 2, "qty": 5, "price": "9.90"}, {"order_id": O1, "line": 10, "qty": 1, "price": "100"},
             {"order_id": O1, "line": 1, "qty": 2, "price": "0.50"}]
    h = table_hash(LINES, ["order_id", "line"], lines)
    assert h == table_hash(LINES, ["order_id", "line"], list(reversed(lines)))
    cases.append({"id": "table-hash", "description": "rows sorted by their canonical primary key's bytes (line 10 sorts "
                  "before line 2: \"10\" < \"2\"), each 8-byte big-endian length then the row; the input's order does not matter",
                  "input": {"columns": LINES, "pk": ["order_id", "line"], "rows": lines}, "expected": {"sha256": h}})

    orders = [{"id": O1, "legal_entity": LE, "code": "SO-1", "note": None, "total": "1250.5", "lines": 3,
               "closed_at": "2026-03-01T07:00:00Z", "day": "2026-03-01", "paid": True, "attrs": None, "blob": None}]
    tables = [{"name": "orders", "columns": ORDERS, "pk": ["id"], "rows": orders},
              {"name": "order_lines", "columns": LINES, "pk": ["order_id", "line"], "rows": lines}]
    d = unit_digest("sales.orders", "1", tables)
    cases.append({"id": "unit-digest", "description": "two tables, by name; the unit's digest",
                  "input": {"class": "sales.orders", "schema_version": "1", "tables": tables}, "expected": {"digest": d}})
    reordered = [{**tables[0], "columns": dict(reversed(list(ORDERS.items())))}, tables[1]]
    assert unit_digest("sales.orders", "1", list(reversed(reordered))) == d
    cases.append({"id": "unit-digest-column-order", "description": "the same content with the columns and the tables "
                  "listed in another order: the same digest (independent of the file's layout)",
                  "input": {"class": "sales.orders", "schema_version": "1", "tables": list(reversed(reordered))},
                  "expected": {"digest": d}})
    changed = [{**tables[0], "rows": [{**orders[0], "note": ""}]}, tables[1]]
    cases.append({"id": "unit-digest-null-vs-empty", "description": "a null became an empty string: another digest",
                  "input": {"class": "sales.orders", "schema_version": "1", "tables": changed},
                  "expected": {"digest": unit_digest("sales.orders", "1", changed)}})
    assert cases[-1]["expected"]["digest"] != d
    write("tier-digest", ["P15.8", "P15.9", "P15.10"],
          "规范行（按列的类型，null 不写）、主键的规范形式、表的散列（按主键排序，长度前缀）与单元的摘要",
          cases, {"input": "columns, row | pk | rows | class, schema_version, tables",
                  "expected": "canonical_row | refused | canonical_pk | sha256 | digest"})


def object_key(prefix, cls, unit, generation, version, table, part):
    return f"{prefix}/{cls}/{unit}/{generation}.{version}/{table}-{part}.parquet"


def manifest_vectors():
    unit = "0190f3a1-0000-7000-8000-0000000000c1"
    cases = [{"id": "object-key", "description": "the component's prefix, the class, the unit, generation.version, "
              "the table and the part", "input": {"prefix": "sales", "class": "sales.orders", "unit": unit,
                                                 "generation": 3, "version": 1, "table": "order_lines", "part": 0},
              "expected": {"key": object_key("sales", "sales.orders", unit, 3, 1, "order_lines", 0)}}]
    m = {"record_type": "be.tier.manifest", "schema": "1.0", "unit": unit, "class": "sales.orders", "version": 1,
         "route": "object-parquet", "generation": 3, "epoch": "1.1", "format": "parquet-1", "schema_version": "1",
         "digest_version": 1, "digest": "sha256:" + "0" * 64,
         "tables": [{"name": "order_lines", "pk": ["order_id", "line"],
                     "columns": [{"name": "line", "type": "int4", "nullable": False},
                                 {"name": "order_id", "type": "uuid", "nullable": False}],
                     "rows": "3", "objects": [{"key": object_key("sales", "sales.orders", unit, 3, 1, "order_lines", 0),
                                               "rows": "3", "bytes": "1024", "sha256": "1" * 64}]}],
         "created_at": "2026-11-06T10:00:00.000000Z"}
    cases.append({"id": "manifest-canonical", "description": "a manifest's canonical bytes (counts as decimal strings)",
                  "input": {"manifest": m}, "expected": {"canonical": canonical(m).decode()}})
    write("tier-manifest", ["P15.15", "P15.16"], "对象的键与清单的规范形式", cases,
          {"input": "prefix, class, unit, generation, version, table, part | manifest", "expected": "key | canonical"})


TIERABLE = {"completed_history", "audit_evidence"}
BLOCKED_ALERT_DAYS = 30


def at(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def plan(now, n_days, grace_days, cls, u):
    """One unit's action and the reasons it is held back (P15.37)."""
    now = at(now)
    if cls["category"] not in TIERABLE:
        return {"action": "none", "reasons": ["not_tierable"]}
    if cls["residence_days"] != "never" and cls["residence_days"] < n_days:
        return {"action": "none", "reasons": ["residence_below_n"]}
    state = u["state"]
    if state == "destroyed":
        return {"action": "none", "reasons": []}
    if state != "open" and u.get("retention_due"):
        reasons = []
        if cls["retention"] == "pending":
            reasons.append("retention_pending")
        if u.get("holds", 0) > 0:
            reasons.append("held")
        if not u.get("approved"):
            reasons.append("approval")
        return {"action": "none" if reasons else "destroy", "reasons": sorted(reasons)}
    if state == "open":
        if cls["residence_days"] == "never":
            return {"action": "none", "reasons": ["never"]}
        due = at(u["anchor_max"]) + timedelta(days=cls["residence_days"])
        if due > now:
            return {"action": "none", "reasons": ["residence"]}
        if u.get("blockers"):
            out = {"action": "none", "reasons": sorted(u["blockers"])}
            if now >= due + timedelta(days=BLOCKED_ALERT_DAYS):
                out["alert"] = True
            return out
        return {"action": "seal", "reasons": []}
    if state == "sealed":
        if u.get("route_immutable") and cls.get("erasable"):
            return {"action": "none", "reasons": ["immutable_route"]}
        return {"action": "transfer", "reasons": []}
    if state == "published":
        reasons = []
        if at(u["published_at"]) + timedelta(days=grace_days) > now:
            reasons.append("grace")
        if at(u["newest_created"]) > now - timedelta(days=n_days):
            reasons.append("recent_records")
        if u.get("old_leases", 0) > 0:
            reasons.append("lease")
        if not u.get("backup_after_publish"):
            reasons.append("no_backup")
        return {"action": "none" if reasons else "release", "reasons": sorted(reasons)}
    return {"action": "none", "reasons": []}  # released


def plan_vectors():
    now, n, grace = "2026-11-06T00:00:00Z", 90, 7
    sales = {"category": "completed_history", "residence_days": 365, "retention": {"min_days": 3650}, "erasable": True}
    six = {**sales, "residence_days": 180}
    cases = []

    def case(cid, description, cls, unit, want):
        got = plan(now, n, grace, cls, unit)
        assert got == want, (cid, got, want)
        cases.append({"id": cid, "description": description,
                      "input": {"now": now, "n_days": n, "grace_days": grace, "class": cls, "unit": unit},
                      "expected": want})

    case("residence-not-reached", "closed five months ago, residence 12 months (TR28)", sales,
         {"state": "open", "anchor_max": "2026-06-06T00:00:00Z"}, {"action": "none", "reasons": ["residence"]})
    case("residence-shortened", "the same unit after the residence went to 6 months (TR29)", six,
         {"state": "open", "anchor_max": "2026-05-01T00:00:00Z"}, {"action": "seal", "reasons": []})
    case("residence-below-n", "a residence of 30 days is below N (TR29)", {**sales, "residence_days": 30},
         {"state": "open", "anchor_max": "2025-01-01T00:00:00Z"}, {"action": "none", "reasons": ["residence_below_n"]})
    case("never", "a class set to stay online", {**sales, "residence_days": "never"},
         {"state": "open", "anchor_max": "2020-01-01T00:00:00Z"}, {"action": "none", "reasons": ["never"]})
    case("blocked", "past the residence, a reservation still open (TR30)", sales,
         {"state": "open", "anchor_max": "2025-10-20T00:00:00Z", "blockers": ["reservation_open"]},
         {"action": "none", "reasons": ["reservation_open"]})
    case("blocked-alert", "blocked 30 days past the residence: alert (TR30)", sales,
         {"state": "open", "anchor_max": "2025-09-01T00:00:00Z", "blockers": ["reservation_open", "period_open"]},
         {"action": "none", "reasons": ["period_open", "reservation_open"], "alert": True})
    case("not-tierable", "an online mutable class is never tiered (TR22)", {**sales, "category": "online_mutable"},
         {"state": "open", "anchor_max": "2020-01-01T00:00:00Z"}, {"action": "none", "reasons": ["not_tierable"]})
    case("audit", "audit evidence tiers like completed history", {**sales, "category": "audit_evidence"},
         {"state": "open", "anchor_max": "2025-01-01T00:00:00Z"}, {"action": "seal", "reasons": []})
    case("sealed", "a sealed unit is transferred", sales, {"state": "sealed"}, {"action": "transfer", "reasons": []})
    case("immutable-route", "an erasable class does not go to a locked route", sales,
         {"state": "sealed", "route_immutable": True}, {"action": "none", "reasons": ["immutable_route"]})
    base = {"state": "published", "published_at": "2026-10-01T00:00:00Z", "newest_created": "2025-01-01T00:00:00Z",
            "old_leases": 0, "backup_after_publish": True}
    case("release", "every release condition holds", sales, base, {"action": "release", "reasons": []})
    case("release-grace", "published two days ago", sales, {**base, "published_at": "2026-11-04T00:00:00Z"},
         {"action": "none", "reasons": ["grace"]})
    case("release-recent", "a record created 30 days ago (TR25)", sales, {**base, "newest_created": "2026-10-07T00:00:00Z"},
         {"action": "none", "reasons": ["recent_records"]})
    case("release-lease", "an export still reading the old route (TR06)", sales, {**base, "old_leases": 1},
         {"action": "none", "reasons": ["lease"]})
    case("release-no-backup", "no backup since the publish", sales, {**base, "backup_after_publish": False},
         {"action": "none", "reasons": ["no_backup"]})
    case("released", "nothing more until its retention", sales, {"state": "released"}, {"action": "none", "reasons": []})
    case("destroy", "retention over, approved, no hold", sales, {"state": "released", "retention_due": True, "approved": True},
         {"action": "destroy", "reasons": []})
    case("destroy-held", "retention over but a legal hold (TR13)", sales,
         {"state": "released", "retention_due": True, "approved": True, "holds": 1}, {"action": "none", "reasons": ["held"]})
    case("destroy-pending", "a retention without a basis is never destroyed (TR24)", {**sales, "retention": "pending"},
         {"state": "released", "retention_due": True, "approved": True}, {"action": "none", "reasons": ["retention_pending"]})
    case("destroy-unapproved", "the class's approval not done", sales, {"state": "published", "retention_due": True},
         {"action": "none", "reasons": ["approval"]})
    case("destroyed", "a destroyed unit", sales, {"state": "destroyed"}, {"action": "none", "reasons": []})
    write("tier-plan", ["P15.3", "P15.4", "P15.11", "P15.19", "P15.29", "P15.32", "P15.37"],
          "规划：每个单元的动作（none、seal、transfer、release、destroy）与被阻塞的原因",
          cases, {"input": "now, n_days, grace_days, class, unit", "expected": "action, reasons, alert"})
