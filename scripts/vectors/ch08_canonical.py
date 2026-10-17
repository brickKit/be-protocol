"""Chapter 08: canonical encoding and digests (P8.8; assembly project security 09a)."""
import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from decimal import Context, Decimal, InvalidOperation

EXACT = Context(prec=1000)  # no rounding: the default context rounds to 28 digits

from common import write


class Refused(Exception):
    pass


def norm_decimal(s):
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise Refused("decimal")
    if not d.is_finite():
        raise Refused("decimal")
    if d == 0:
        return "0"
    t = d.normalize(EXACT)
    sign, digits, exp = t.as_tuple()
    if len(digits) > 38 or (exp < 0 and -exp > 18):
        raise Refused("decimal")
    out = format(t, "f")
    if "." in out:
        out = out.rstrip("0").rstrip(".")
    return out


def norm_instant(s):
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        raise Refused("instant")
    if t.tzinfo is None:
        raise Refused("instant")
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def check(v):
    if v is None or isinstance(v, float):
        raise Refused("json")
    if isinstance(v, bool):
        return
    if isinstance(v, int) and abs(v) >= 2 ** 53:
        raise Refused("json")
    if isinstance(v, list):
        for x in v:
            check(x)
    if isinstance(v, dict):
        for x in v.values():
            check(x)


def canonical(v):
    check(v)
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def digest(record_type, major, v):
    return "sha256:" + hashlib.sha256(f"{record_type}.v{major}\n".encode() + canonical(v)).hexdigest()


def sorted_set(items):
    seen = {}
    for x in items:
        seen[canonical(x)] = x
    return [seen[k] for k in sorted(seen)]


def norm_atom(a):
    a = dict(a)
    if a["kind"] == "in":
        a["values"] = sorted_set([unicodedata.normalize("NFC", v) for v in a["values"]])
    elif a["kind"] == "tree":
        a["items"] = sorted_set(a["items"])
    elif a["kind"] == "interval":
        for k in ("lo", "hi"):
            if k in a:
                a[k] = norm_decimal(a[k])
    return a


def norm_segment(seg):
    seg = dict(seg)
    seg.pop("digest", None)
    seg["atoms"] = {k: norm_atom(v) for k, v in seg["atoms"].items()}
    seg["read_fields"] = sorted_set(seg["read_fields"])
    seg["write_fields"] = sorted_set(seg["write_fields"])
    seg["valid"] = {k: norm_instant(v) for k, v in seg["valid"].items()}
    return seg


def canonical_vectors():
    cases = []

    def add(cid, kind, value, **kw):
        c = {"id": cid, "kind": kind, "in": value}
        c.update(kw)
        try:
            if kind == "decimal":
                c["expect"] = {"out": norm_decimal(value)}
            elif kind == "instant":
                c["expect"] = {"out": norm_instant(value)}
            elif kind == "text":
                c["expect"] = {"out": unicodedata.normalize("NFC", value)}
            elif kind == "json":
                c["expect"] = {"out": canonical(value).decode()}
            elif kind == "digest":
                c["expect"] = {"out": digest(kw["record_type"], kw["major"], value)}
            elif kind == "segment":
                n = norm_segment(value)
                c["expect"] = {"canonical": canonical(n).decode(), "digest": digest("be.security.segment", 1, n)}
        except Refused as r:
            c["expect"] = {"refused": str(r)}
        cases.append(c)

    for cid, v in [("trailing-zeros", "100.00"), ("exponent", "1E2"), ("negative-zero", "-0.0"),
                   ("fraction", "0.500"), ("leading-plus", "+1"), ("leading-zeros", "00012.3400"),
                   ("negative", "-12.3400"), ("small-exponent", "1e-18"), ("too-many-digits", "1" * 39),
                   ("too-many-fraction-digits", "0.0000000000000000001"), ("not-a-number", "abc"),
                   ("infinity", "Infinity"), ("integer", "42")]:
        add("decimal-" + cid, "decimal", v)
    for cid, v in [("offset", "2026-10-17T10:00:00+08:00"), ("fraction", "2026-10-17T02:00:00.5Z"),
                   ("utc", "2026-10-17T02:00:00Z"), ("no-zone", "2026-10-17T02:00:00"),
                   ("negative-offset", "2026-10-16T21:30:00.123456-04:30")]:
        add("instant-" + cid, "instant", v)
    add("text-nfc", "text", "é café")
    for cid, v in [("key-order", {"b": 1, "a": [True, False], "c": {"z": "1", "y": "2"}}),
                   ("escapes", {"s": "quote\" back\\ nl\n tab\t ctl\u0001 del\u007f slash/"}),
                   ("unicode", {"s": "仓库 é \U0001F600  "}),
                   ("integers", {"a": 0, "b": -1, "c": 9007199254740991}),
                   ("null", {"a": None}), ("float", {"a": 1.5}), ("too-large-integer", {"a": 2 ** 53}),
                   ("nested-arrays", [[], [{}], ["x", 1]])]:
        add("json-" + cid, "json", v)
    rec = {"type": "demo.order", "fields": ["cost", "number"]}
    add("digest-resource", "digest", rec, record_type="be.security.resource_definition", major=1)
    add("digest-same-json-other-type", "digest", rec, record_type="be.security.operation_definition", major=1)
    add("digest-same-json-other-major", "digest", rec, record_type="be.security.resource_definition", major=2)
    seg = {"resource_type": "demo.order", "operation": "demo.order.read",
           "atoms": {"legal_entity": {"kind": "in", "values": ["LE2", "LE1", "LE2"]},
                     "dept": {"kind": "tree", "items": [{"path": "org1/org3", "mode": "subtree"},
                                                        {"path": "org1/org2", "mode": "exact"}]},
                     "amount": {"kind": "interval", "currency": "CNY", "lo": "0.00", "lo_closed": True,
                                "hi": "1E4", "hi_closed": False},
                     "owner": {"kind": "all"}},
           "read_fields": ["number", "cost", "number"], "write_fields": [],
           "valid": {"from": "2026-10-17T08:00:00+08:00"},
           "source": "0190f3a1-7b2c-7def-8a01-23456789abcd",
           "definition": {"owner_component": "demo/orders", "kind": "resource", "key": "demo.order", "version": "1",
                          "digest": "sha256:" + "0" * 64}}
    add("segment-normalized", "segment", seg)
    reordered = json.loads(json.dumps(seg))
    reordered["atoms"]["legal_entity"]["values"] = ["LE1", "LE2"]
    reordered["atoms"]["amount"]["lo"], reordered["atoms"]["amount"]["hi"] = "0", "10000.000"
    reordered["valid"]["from"] = "2026-10-17T00:00:00Z"
    reordered["read_fields"] = ["cost", "number"]
    reordered["digest"] = "sha256:ignored"
    add("segment-same-meaning", "segment", reordered)
    write("canonical", ["P8.8"],
          "规范编码（装配项目安全 09a）：kind=decimal、instant、text 是单个值的规范形式；json 是 RFC 8785 的规范字节（这里写成 UTF-8 "
          "字符串）；digest 是 sha256:（<记录类型>.v<主版本> + 换行 + 规范字节）；segment 是授予段的规范化（集合按元素的规范字节排序去重、"
          "十进制与时刻规范化、排除 digest 字段）后的规范字节与摘要，两份语义相同的段摘要相同。expect.refused 表示拒绝（null、浮点数、"
          "绝对值不小于 2^53 的整数、不合规的十进制或时刻）。",
          cases, {"kind": "decimal | instant | text | json | digest | segment", "in": "输入",
                  "record_type、major": "digest 的域前缀", "expect": "out、canonical 与 digest，或 refused"})
