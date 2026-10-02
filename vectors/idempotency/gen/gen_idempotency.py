#!/usr/bin/env python3
"""Generate vectors/idempotency/*.json (protocol P3.7, P13; foundations 11).

The request fingerprint is SHA-256 over the RFC 8785 (JCS) canonical form of
the fingerprint object. The canonicaliser below is written from the RFC text
with the standard library only; xcheck_idempotency.mjs recomputes every case
with the npm package `canonicalize` (the RFC authors' JavaScript reference)
and Node's crypto.
"""

import datetime as dt
import hashlib
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_lib"))
from vecfile import CaseList, area_dir, write_file  # noqa: E402

GEN = "idempotency/gen/gen_idempotency.py"
OUT = area_dir(__file__)


class FpError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------- JSON input (I-JSON)

def _reject_constant(name):
    raise FpError("JSON_INVALID")  # NaN, Infinity, -Infinity are not JSON


def _pairs(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise FpError("JSON_INVALID")  # RFC 7493 (I-JSON): member names must be unique
    return dict(pairs)


def _num(text):
    v = float(text)  # every JSON number is an IEEE 754 double (RFC 8785 §3.2.2.3)
    if math.isinf(v) or math.isnan(v):
        raise FpError("JSON_INVALID")
    return v


def load(text):
    try:
        return json.loads(text, parse_float=_num, parse_int=_num, parse_constant=_reject_constant,
                          object_pairs_hook=_pairs)
    except FpError:
        raise
    except ValueError:
        raise FpError("JSON_INVALID")


# ---------------------------------------------------------------- JCS (RFC 8785)

def es_number(x):
    """ECMAScript Number::toString for a finite double (RFC 8785 §3.2.2.3)."""
    if x == 0:
        return "0"
    if x < 0:
        return "-" + es_number(-x)
    r = repr(x)  # shortest round-trip digits, same digit string as ECMAScript
    if "e" in r:
        mant, exp = r.split("e")
        exp = int(exp)
    else:
        mant, exp = r, 0
    if "." in mant:
        ip, fp = mant.split(".")
    else:
        ip, fp = mant, ""
    if fp == "0":
        fp = ""
    digits = (ip + fp).lstrip("0")
    lead = len(ip + fp) - len((ip + fp).lstrip("0"))
    n = len(ip) + exp - lead  # value = 0.digits * 10^n
    digits = digits.rstrip("0")
    k = len(digits)
    if k <= n <= 21:
        return digits + "0" * (n - k)
    if 0 < n <= 21:
        return digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return "0." + "0" * (-n) + digits
    e = n - 1
    es = ("+" if e >= 0 else "-") + str(abs(e))
    if k == 1:
        return digits + "e" + es
    return digits[0] + "." + digits[1:] + "e" + es


def jcs(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, float):
        return es_number(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ",".join(jcs(x) for x in v) + "]"
    if isinstance(v, dict):
        keys = sorted(v, key=lambda k: k.encode("utf-16-be"))  # UTF-16 code units
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + jcs(v[k]) for k in keys) + "}"
    raise TypeError(type(v))


def fingerprint(text):
    canon = jcs(load(text))
    return {"canonical": canon, "sha256": hashlib.sha256(canon.encode("utf-8")).hexdigest()}


def add_fp(c, slug, desc, text, refs=("P13.2",)):
    try:
        c.add(slug, desc, "fingerprint", {"json_text": text}, expected=fingerprint(text), refs=list(refs))
    except FpError as e:
        c.add(slug, desc, "fingerprint", {"json_text": text}, error=e.reason, refs=list(refs))


def ieee(h):
    import struct
    return struct.unpack(">d", bytes.fromhex(h))[0]


# ---------------------------------------------------------------- cases

def gen_fingerprint():
    c = CaseList("idempotency", "fingerprint")
    # RFC 8785 §3.2.2.3, the IEEE 754 sample table: the generator writes the
    # number with Python's repr (a valid JSON number text, often not the
    # canonical one) and checks its own output against the RFC's column.
    rfc_table = [
        ("0000000000000000", "0"), ("8000000000000000", "0"), ("0000000000000001", "5e-324"),
        ("8000000000000001", "-5e-324"), ("7fefffffffffffff", "1.7976931348623157e+308"),
        ("ffefffffffffffff", "-1.7976931348623157e+308"), ("4340000000000000", "9007199254740992"),
        ("c340000000000000", "-9007199254740992"), ("4430000000000000", "295147905179352830000"),
        ("44b52d02c7e14af5", "9.999999999999997e+22"), ("44b52d02c7e14af6", "1e+23"),
        ("44b52d02c7e14af7", "1.0000000000000001e+23"), ("444b1ae4d6e2ef4e", "999999999999999700000"),
        ("444b1ae4d6e2ef4f", "999999999999999900000"), ("444b1ae4d6e2ef50", "1e+21"),
        ("3eb0c6f7a0b5ed8c", "9.999999999999997e-7"), ("3eb0c6f7a0b5ed8d", "0.000001"),
        ("41b3de4355555553", "333333333.3333332"), ("41b3de4355555554", "333333333.33333325"),
        ("41b3de4355555555", "333333333.3333333"), ("41b3de4355555556", "333333333.3333334"),
        ("41b3de4355555557", "333333333.33333343"), ("becbf647612f3696", "-0.0000033333333333333333"),
        ("43143ff3c1cb0959", "1424953923781206.2"),
    ]
    for h, want in rfc_table:
        x = ieee(h)
        text = '{"n":' + repr(x) + '}'
        got = fingerprint(text)["canonical"]
        assert got == '{"n":' + want + "}", (h, got, want)
        add_fp(c, "rfc8785-number-" + h, f"RFC 8785 number sample 0x{h} written as {repr(x)}", text,
               refs=("P13.2", "RFC8785-3.2.2.3"))
    for slug, text, why in [
        ("rfc8785-nan", '{"n":NaN}', "NaN is not JSON"),
        ("rfc8785-infinity", '{"n":Infinity}', "Infinity is not JSON"),
        ("overflow-to-infinity", '{"n":1e400}', "a number that overflows a double"),
        ("negative-overflow", '{"n":-1e400}', "a negative number that overflows a double"),
        ("duplicate-key", '{"a":1,"a":2}', "duplicate member names (I-JSON)"),
        ("trailing-comma", '{"a":1,}', "not JSON"),
        ("single-quotes", "{'a':1}", "not JSON"),
        ("leading-zero", '{"a":01}', "not JSON"),
        ("hex-number", '{"a":0x10}', "not JSON"),
        ("plus-sign", '{"a":+1}', "not JSON"),
        ("empty-text", "", "no value"),
    ]:
        add_fp(c, slug, f"rejected input: {why}", text)
    for slug, text, why in [
        ("int-and-float-equal", '{"qty":1}', "1"),
        ("float-one", '{"qty":1.0}', "1.0 canonicalises to 1, same hash as 1"),
        ("exponent-one", '{"qty":1E0}', "1E0 canonicalises to 1"),
        ("hundredths", '{"qty":100e-2}', "100e-2 is 1"),
        ("negative-zero", '{"qty":-0}', "-0 canonicalises to 0"),
        ("negative-zero-float", '{"qty":-0.0}', "-0.0 canonicalises to 0"),
        ("small", '{"x":1e-7}', "below 1e-6 uses the exponent form"),
        ("small-fixed", '{"x":0.000001}', "1e-6 is still fixed notation"),
        ("large-fixed", '{"x":1e20}', "1e20 is fixed notation"),
        ("large-exponent", '{"x":1e21}', "1e21 switches to the exponent form"),
        ("beyond-2-53", '{"id":9007199254740993}', "an integer beyond 2^53 collapses to the nearest double"),
        ("big-integer", '{"id":123456789012345678901234567890}', "a 30-digit integer"),
        ("string-number-differs", '{"qty":"1"}', "a string is not a number: different hash from 1"),
        ("money-as-string", '{"amount":"12.30","currency":"CNY"}', "money stays a string, trailing zero kept"),
        ("money-as-string-no-zero", '{"amount":"12.3","currency":"CNY"}', "'12.3' is a different string from '12.30'"),
    ]:
        add_fp(c, slug, f"numbers: {why}", text)
    rfc_obj = ('{"numbers": [333333333.33333329, 1E30, 4.50, 2e-3, 0.000000000000000000000000001],'
               ' "string": "\\u20ac$\\u000F\\u000aA\'\\u0042\\u0022\\u005c\\\\\\"\\/",'
               ' "literals": [null, true, false]}')
    want = '{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],"string":"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'
    assert fingerprint(rfc_obj)["canonical"] == want, fingerprint(rfc_obj)["canonical"]
    add_fp(c, "rfc8785-example", "the RFC 8785 §3.2.4 example object", rfc_obj, refs=("P13.2", "RFC8785-3.2.4"))
    sort_obj = ('{"\\u20ac": "Euro Sign", "\\r": "Carriage Return", "\\ufb33": "Hebrew Letter Dalet With Dagesh",'
                ' "1": "One", "\\ud83d\\ude00": "Emoji: Grinning Face", "\\u0080": "Control",'
                ' "\\u00f6": "Latin Small Letter O With Diaeresis"}')
    keys = [k for k in json.loads(fingerprint(sort_obj)["canonical"])]
    assert keys == ["\r", "1", "\u0080", "ö", "€", "\U0001F600", "דּ"], keys
    add_fp(c, "rfc8785-sorting", "the RFC 8785 §3.2.3 sorting example: UTF-16 code units, not code points",
           sort_obj, refs=("P13.2", "RFC8785-3.2.3"))
    for slug, text, why in [
        ("key-order-a", '{"b":2,"a":1}', "keys are sorted"),
        ("key-order-b", '{"a":1,"b":2}', "same hash as key-order-a"),
        ("nested-sort", '{"z":{"y":1,"x":[{"b":1,"a":2}]},"a":null}', "nested objects inside arrays are sorted too"),
        ("array-order-a", '{"items":["p1","p2"]}', "array order is kept"),
        ("array-order-b", '{"items":["p2","p1"]}', "different hash from array-order-a"),
        ("whitespace", ' {\n  "a" : 1 ,\t"b":[ 1 , 2 ] }\r\n', "insignificant whitespace is dropped"),
        ("empty-object", "{}", "empty object"),
        ("empty-array", "[]", "a top-level array"),
        ("nested-empty", '{"a":{},"b":[],"c":""}', "empty containers and string"),
        ("literals", '{"t":true,"f":false,"n":null}', "literals"),
        ("cjk-value", '{"name":"华东一仓"}', "CJK stays raw UTF-8"),
        ("cjk-keys", '{"仓库":"1","客户":"2","a":"3"}', "CJK keys sort after ASCII by UTF-16 unit"),
        ("nfc", '{"name":"caf\\u00e9"}', "precomposed é (NFC)"),
        ("nfd", '{"name":"cafe\\u0301"}', "decomposed é (NFD): no normalisation, different hash from nfc"),
        ("emoji-escaped", '{"e":"\\ud83d\\ude00"}', "a surrogate pair escape becomes raw UTF-8"),
        ("emoji-raw", '{"e":"😀"}', "same hash as emoji-escaped"),
        ("astral-vs-bmp-key", '{"\\ud83d\\ude00":1,"\\uffff":2}', "U+1F600 sorts before U+FFFF by UTF-16 unit"),
        ("control-chars", '{"s":"\\u0000\\u0001\\u001f\\b\\t\\n\\f\\r"}', "controls: short escapes where they exist, else \\u00xx lower case"),
        ("del-and-separators", '{"s":"\\u007f\\u2028\\u2029"}', "DEL, U+2028 and U+2029 are not escaped"),
        ("slash", '{"s":"a\\/b"}', "an escaped solidus is written as /"),
        ("quote-backslash", '{"s":"\\"\\\\"}', "quote and backslash are escaped"),
        ("unicode-escape-upper", '{"s":"\\u00C9"}', "\\u00C9 decodes to É, written raw"),
        ("request-create-widget",
         '{"name":"Widget A","kind_code":"STD","region":"east","legal_entity_id":"LE01",'
         '"currency":"CNY","price":"12.500000","quantity":"2","lines":[{"line_no":1,"description":"x"}]}',
         "a typical create request"),
        ("request-create-widget-reordered",
         '{"lines":[{"description":"x","line_no":1}],"quantity":"2","price":"12.500000","currency":"CNY",'
         '"legal_entity_id":"LE01","region":"east","kind_code":"STD","name":"Widget A"}',
         "the same request with every key reordered: same hash"),
    ]:
        add_fp(c, slug, why, text)
    return c


def ns(caller):
    k = caller["kind"]
    if k == "user":
        return "user:" + caller["sub"]
    if k == "system_call":
        return "svc:" + caller["be_caller"]
    if k == "background":
        return "system"
    raise KeyError(k)


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def decide(inp):
    inc = inp["incoming"]
    caller = ns(inc["caller"])
    now = ts(inp["now"])
    h = fingerprint(inc["request"])["sha256"]
    row = None
    for r in inp["rows"]:
        if r["caller"] == caller and r["idempotency_key"] == inc["key"]:
            row = r
    if row is None or now >= ts(row["expires_at"]):
        return {"caller": caller, "outcome": "EXECUTE"}
    if (row["command"] != inc["command"] or row["target"] != inc["target"]
            or row["request_hash"] != h):
        return {"caller": caller, "outcome": "REJECT", "code": "INVALID_ARGUMENT", "http": 400,
                "reason": "IDEMPOTENCY_MISMATCH"}
    if row["status"] == "CLAIMED":
        return {"caller": caller, "outcome": "REJECT", "code": "ABORTED", "http": 409,
                "reason": "IDEMPOTENCY_IN_PROGRESS"}
    return {"caller": caller, "outcome": "REPLAY", "result": row["result"]}


def gen_decide():
    c = CaseList("idempotency", "decide")
    body = '{"name":"Widget A","price":"12.50"}'
    body2 = '{"name":"Widget A","price":"12.60"}'
    hb = fingerprint(body)["sha256"]
    user = {"kind": "user", "sub": "0192f0c4-7b1e-7cc3-9a52-3f1d2e4b5a60"}
    other = {"kind": "user", "sub": "0192f0c4-7b1e-7cc3-9a52-3f1d2e4b5a61"}
    svc = {"kind": "system_call", "be_caller": "erp/sales"}
    bg = {"kind": "background"}
    K = "0192f0c5-0000-7000-8000-000000000001"
    done = {"caller": "user:" + user["sub"], "idempotency_key": K, "command": "conformance.widget.create",
            "target": "", "request_hash": hb, "status": "DONE",
            "result": {"http": 201, "body": {"id": "0192f0c5-1111-7000-8000-000000000001"}},
            "created_at": "2026-10-01T00:00:00Z", "expires_at": "2026-10-31T00:00:00Z"}
    claimed = dict(done, status="CLAIMED", result=None, command="conformance.widget.approve",
                   target="0192f0c5-1111-7000-8000-000000000001")
    inc = lambda **kw: dict({"caller": user, "key": K, "command": "conformance.widget.create",  # noqa: E731
                             "target": "", "request": body}, **kw)
    rows = [
        ("first-use", [], inc(), "no row for (caller, key): claim and execute"),
        ("replay-done", [done], inc(), "same caller, key, command, target and body: replay the stored result"),
        ("replay-reordered-body", [done], inc(request='{"price":"12.50","name":"Widget A"}'),
         "the body differs only in key order: same fingerprint, replay"),
        ("mismatch-body", [done], inc(request=body2), "a different body under the same key"),
        ("mismatch-command", [done], inc(command="conformance.widget.approve"), "a different command"),
        ("mismatch-target", [done], inc(target="0192f0c5-1111-7000-8000-000000000002"), "a different target"),
        ("in-progress", [claimed], inc(command="conformance.widget.approve", target=claimed["target"]),
         "the first use is still CLAIMED (two-step command)"),
        ("in-progress-mismatch", [claimed], inc(command="conformance.widget.approve", target=claimed["target"],
                                                 request=body2),
         "CLAIMED and a different body: the mismatch is reported first"),
        ("other-user-same-key", [done], inc(caller=other), "another user's key is, for me, an unused key"),
        ("service-same-key", [done], inc(caller=svc), "the svc: namespace is separate from user:"),
        ("system-same-key", [done], inc(caller=bg), "the system namespace is separate from user:"),
        ("expired", [done], dict(inc(), _now="2026-10-31T00:00:00Z"), "at expires_at the key is new again"),
        ("just-before-expiry", [done], dict(inc(), _now="2026-10-30T23:59:59.999Z"), "one millisecond before expiry: replay"),
    ]
    for slug, rws, incoming, why in rows:
        now = incoming.pop("_now", "2026-10-02T08:00:00Z")
        inp = {"rows": rws, "now": now, "incoming": incoming}
        c.add(slug, why, "decide", inp, expected=decide(inp), refs=["P13.1", "P13.2", "P13.3", "P13.4", "P13.7"])
    return c


def resolve_key(inp):
    h, b = inp.get("header"), inp.get("body")
    if h is not None and b is not None and h != b:
        raise FpError("IDEMPOTENCY_MISMATCH")
    return {"key": h if h is not None else b}


def gen_keys():
    c = CaseList("idempotency", "keys")
    K1, K2 = "0192f0c5-0000-7000-8000-000000000001", "0192f0c5-0000-7000-8000-000000000002"
    for slug, inp, why in [
        ("header-only", {"header": K1, "body": None}, "Idempotency-Key header only"),
        ("body-only", {"header": None, "body": K1}, "idempotency_key body field only"),
        ("both-equal", {"header": K1, "body": K1}, "both present and equal"),
        ("both-differ", {"header": K1, "body": K2}, "both present and different: 400"),
        ("neither", {"header": None, "body": None}, "no key: the command runs without idempotency"),
    ]:
        try:
            c.add(slug, why, "resolve_key", inp, expected=resolve_key(inp), refs=["P3.7"])
        except FpError as e:
            c.add(slug, why, "resolve_key", inp,
                  error={"reason": e.reason, "code": "INVALID_ARGUMENT", "http": 400}, refs=["P3.7"])
    for slug, caller, why in [
        ("ns-user", {"kind": "user", "sub": "0192f0c4-7b1e-7cc3-9a52-3f1d2e4b5a60"}, "a user request"),
        ("ns-system-call", {"kind": "system_call", "be_caller": "erp/sales"}, "a gRPC system call from erp/sales"),
        ("ns-shell-member", {"kind": "system_call", "be_caller": "conformance/widget-go"}, "be-caller is the member's ID"),
        ("ns-background", {"kind": "background"}, "the component's own job or event handler"),
    ]:
        c.add(slug, "caller namespace for " + why, "caller_namespace", {"caller": caller},
              expected={"caller": ns(caller)}, refs=["P13.1"])
    for slug, created in [("expiry", "2026-10-02T08:00:00Z"), ("expiry-leap", "2028-02-15T23:30:00.123456Z"),
                          ("expiry-month-end", "2026-01-31T00:00:00Z")]:
        e = ts(created) + dt.timedelta(days=30)
        c.add(slug, "a key expires exactly 30 days (720 h) after it was claimed", "expires_at",
              {"created_at": created}, expected={"expires_at": e.strftime("%Y-%m-%dT%H:%M:%S.%f").rstrip("0").rstrip(".") + "Z"},
              refs=["P13.7"])
    return c


def main():
    counts = {}
    for topic, fn in [("fingerprint", gen_fingerprint), ("decide", gen_decide), ("keys", gen_keys)]:
        counts[topic] = write_file(os.path.join(OUT, f"{topic}.json"), "idempotency", topic, GEN, fn())
    print("idempotency", counts, "total", sum(counts.values()))


if __name__ == "__main__":
    main()
