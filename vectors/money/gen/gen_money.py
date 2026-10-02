#!/usr/bin/env python3
"""Generate vectors/money/*.json (protocol P11.6, foundations 06).

Reference semantics, written once here and checked independently by
xcheck_money.go (Go math/big, no shared code):

* decimal strings: ^-?[0-9]+(\\.[0-9]+)?$ and nothing else;
* capacity per column kind (precision, scale);
* rounding modes HALF_AWAY_FROM_ZERO (default) and HALF_EVEN;
* minor units from ISO 4217 List One (vendored XML next to this file);
* allocation by largest remainder, ties to the earlier line, sign handled on
  the absolute value;
* tax per line / per document.
All arithmetic is exact (fractions.Fraction); no float is ever involved.
"""

import os
import re
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_lib"))
from vecfile import CaseList, area_dir, write_file  # noqa: E402

GEN = "money/gen/gen_money.py"
OUT = area_dir(__file__)
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- reference

SYNTAX = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
CCY_SYNTAX = re.compile(r"^[A-Z]{3}$")
MODES = ("HALF_AWAY_FROM_ZERO", "HALF_EVEN")

KINDS = {  # kind: (precision, scale)
    "amount": (19, 4),
    "price": (19, 6),
    "cost": (19, 6),
    "quantity": (19, 6),
    "rate": (19, 10),
    "ratio": (9, 6),
    "factor": (24, 12),
}


class MoneyError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def load_iso():
    tree = ET.parse(os.path.join(HERE, "iso4217-list-one.xml"))
    root = tree.getroot()
    table = {}
    for e in root.iter("CcyNtry"):
        code = e.findtext("Ccy")
        mnr = e.findtext("CcyMnrUnts")
        fund = (e.find("CcyNm") is not None) and e.find("CcyNm").get("IsFund") == "true"
        if not code or mnr is None or not mnr.strip().isdigit():
            continue  # N.A. minor units: metals, SDR, testing codes
        if fund:
            # funds codes (e.g. CLF, UYI, UYW, BOV, MXV) are kept: CLF is a
            # unit of account used on invoices in Chile and the protocol names it.
            pass
        table[code] = int(mnr)
    return root.get("Pblshd"), table


PUBLISHED, ISO = load_iso()


def parse(s):
    if not isinstance(s, str) or not SYNTAX.fullmatch(s):
        raise MoneyError("DECIMAL_SYNTAX")
    neg = s.startswith("-")
    body = s[1:] if neg else s
    if "." in body:
        ip, fp = body.split(".")
    else:
        ip, fp = body, ""
    v = Fraction(int(ip + fp), 10 ** len(fp))
    return -v if neg else v


def sig_scale(v):
    """Number of significant decimals of an exact decimal value."""
    n = 0
    while (v * 10 ** n).denominator != 1:
        n += 1
        if n > 400:
            raise ValueError("not a terminating decimal")
    return n


def int_digits(v):
    a = abs(v)
    ip = a.numerator // a.denominator
    return 0 if ip == 0 else len(str(ip))


def fmt(v, scale):
    """Exact decimal v (already representable at `scale`) as a fixed string."""
    q = v * 10 ** scale
    assert q.denominator == 1, (v, scale)
    n = q.numerator
    neg = n < 0
    digits = str(abs(n)).rjust(scale + 1, "0")
    out = digits if scale == 0 else digits[:-scale] + "." + digits[-scale:]
    if neg and n != 0:
        out = "-" + out
    return out


def normal(v):
    s = fmt(v, sig_scale(v))
    return s


def check_capacity(v, kind):
    p, sc = KINDS[kind]
    if int_digits(v) > p - sc:
        raise MoneyError("DECIMAL_OVERFLOW")
    if sig_scale(v) > sc:
        raise MoneyError("DECIMAL_SCALE")


def minor(ccy):
    if not isinstance(ccy, str) or not CCY_SYNTAX.fullmatch(ccy):
        raise MoneyError("CURRENCY_INVALID")
    if ccy not in ISO:
        raise MoneyError("CURRENCY_UNKNOWN")
    return ISO[ccy]


def round_to_step(v, step, mode):
    """Round exact v to an integer multiple of exact step > 0."""
    if mode not in MODES:
        raise MoneyError("MODE_UNKNOWN")
    q = v / step
    neg = q < 0
    a = -q if neg else q
    fl = a.numerator // a.denominator
    rem = a - fl
    if rem > Fraction(1, 2):
        r = fl + 1
    elif rem < Fraction(1, 2):
        r = fl
    else:
        r = fl + 1 if mode == "HALF_AWAY_FROM_ZERO" else (fl if fl % 2 == 0 else fl + 1)
    r = -r if neg else r
    return r * step


def round_scale(v, scale, mode):
    return round_to_step(v, Fraction(1, 10 ** scale), mode)


def allocate(total, weights, scale):
    if not weights:
        raise MoneyError("ALLOCATION_INVALID")
    ws = [parse(w) for w in weights]
    if any(w < 0 for w in ws) or sum(ws) == 0:
        raise MoneyError("ALLOCATION_INVALID")
    if sig_scale(total) > scale:
        raise MoneyError("DECIMAL_SCALE")
    unit = Fraction(1, 10 ** scale)
    sign = -1 if total < 0 else 1
    a = abs(total)
    W = sum(ws)
    exact = [a * w / W for w in ws]
    floors = [(e / unit).numerator // (e / unit).denominator for e in exact]
    rems = [e / unit - f for e, f in zip(exact, floors)]
    left = int((a / unit) - sum(floors))
    order = sorted(range(len(ws)), key=lambda i: (-rems[i], i))
    for i in order[:left]:
        floors[i] += 1
    return [sign * f * unit for f in floors]


# ---------------------------------------------------------------- operations
# run(op, input) is the whole reference: every case's expected value or
# expected error comes from it, never from a hand-written literal.

def need_mode(inp):
    mode = inp.get("mode", "HALF_AWAY_FROM_ZERO")
    if mode not in MODES:
        raise MoneyError("MODE_UNKNOWN")
    return mode


def dec_kind(s, kind):
    v = parse(s)
    check_capacity(v, kind)
    return v


def ratio01(s):
    v = dec_kind(s, "ratio")
    if v < 0 or v > 1:
        raise MoneyError("RATIO_INVALID")
    return v


def amount_in(a):
    m = minor(a["currency"])
    v = dec_kind(a["value"], "amount")
    if sig_scale(v) > m:
        raise MoneyError("DECIMAL_SCALE")
    return v, m


def run(op, inp):
    if op == "column":
        k = inp["kind"]
        if k == "currency":
            return {"sql": "CHAR(3)", "precision": None, "scale": None, "integer_digits": None}
        if k not in KINDS:
            raise MoneyError("KIND_UNKNOWN")
        p, s = KINDS[k]
        return {"sql": f"NUMERIC({p},{s})", "precision": p, "scale": s, "integer_digits": p - s}
    if op == "minor_units":
        return {"minor_units": minor(inp["currency"])}
    if op == "parse":
        k = inp["kind"]
        if k != "decimal" and k not in KINDS:
            raise MoneyError("KIND_UNKNOWN")
        v = parse(inp["value"])
        if k != "decimal":
            check_capacity(v, k)
        return {"value": normal(v)}
    if op == "format":
        v = parse(inp["value"])
        m = minor(inp["currency"])
        check_capacity(v, "amount")
        if sig_scale(v) > m:
            raise MoneyError("DECIMAL_SCALE")
        return {"value": fmt(v, m)}
    if op == "round":
        v = parse(inp["value"])
        mode = need_mode(inp)
        sc = minor(inp["currency"]) if "currency" in inp else inp["scale"]
        return {"value": fmt(round_scale(v, sc, mode), sc)}
    if op == "round_cash":
        v = parse(inp["value"])
        m = minor(inp["currency"])
        mode = need_mode(inp)
        inc = parse(inp["increment"])
        if inc <= 0 or sig_scale(inc) > m:
            raise MoneyError("ROUNDING_INVALID")
        return {"value": fmt(round_to_step(v, inc, mode), m)}
    if op == "round_qty":
        v = parse(inp["value"])
        mode = need_mode(inp)
        st = parse(inp["rounding"])
        if st <= 0:
            raise MoneyError("ROUNDING_INVALID")
        return {"value": fmt(round_to_step(v, st, mode), sig_scale(st))}
    if op == "allocate":
        m = minor(inp["currency"])
        total = parse(inp["total"])
        return {"parts": [fmt(p, m) for p in allocate(total, inp["weights"], m)]}
    if op in ("tax_line", "tax_document"):
        m = minor(inp["currency"])
        mode = need_mode(inp)
        rate = ratio01(inp["rate"])
        nets = [amount_in({"value": n, "currency": inp["currency"]})[0] for n in inp["lines"]]
        if op == "tax_line":
            taxes = [round_scale(n * rate, m, mode) for n in nets]
            total = sum(taxes, Fraction(0))
        else:
            total = round_scale(sum(nets, Fraction(0)) * rate, m, mode)
            taxes = allocate(total, inp["lines"], m)
        return {"line_taxes": [fmt(t, m) for t in taxes], "total": fmt(total, m)}
    if op in ("add", "sub"):
        a, m = amount_in(inp["a"])
        b, _ = amount_in(inp["b"])
        if inp["a"]["currency"] != inp["b"]["currency"]:
            raise MoneyError("CURRENCY_MISMATCH")
        v = a + b if op == "add" else a - b
        check_capacity(v, "amount")
        return {"value": fmt(v, m), "currency": inp["a"]["currency"]}
    if op == "convert":
        a, _ = amount_in(inp["amount"])
        m = minor(inp["to"])
        mode = need_mode(inp)
        rate = dec_kind(inp["rate"], "rate")
        if rate <= 0 or (inp["amount"]["currency"] == inp["to"] and rate != 1):
            raise MoneyError("RATE_INVALID")
        v = round_scale(a * rate, m, mode)
        check_capacity(v, "amount")
        return {"value": fmt(v, m), "currency": inp["to"]}
    if op == "line_amount":
        m = minor(inp["currency"])
        mode = need_mode(inp)
        q = dec_kind(inp["quantity"], "quantity")
        p = dec_kind(inp["price"], "price")
        d = ratio01(inp.get("discount", "0"))
        v = round_scale(q * p * (1 - d), m, mode)
        check_capacity(v, "amount")
        return {"value": fmt(v, m), "currency": inp["currency"]}
    raise KeyError(op)


def add(c, slug, desc, op, inp, refs=("P11.6",)):
    try:
        c.add(slug, desc, op, inp, expected=run(op, inp), refs=list(refs))
    except MoneyError as e:
        c.add(slug, desc, op, inp, error=e.reason, refs=list(refs))


HAE, HE = "HALF_AWAY_FROM_ZERO", "HALF_EVEN"

# ---------------------------------------------------------------- cases


def gen_columns():
    c = CaseList("money", "columns")
    for k in list(KINDS) + ["currency", "percent"]:
        add(c, k if k != "percent" else "unknown-kind", f"column specification of kind {k!r}", "column", {"kind": k})
    return c


def gen_currencies():
    c = CaseList("money", "currencies")
    for code in ["CNY", "USD", "EUR", "GBP", "HKD", "MOP", "TWD", "JPY", "KRW", "VND", "IDR", "INR",
                 "SGD", "CHF", "AUD", "CAD", "RUB", "BRL", "KWD", "BHD", "OMR", "JOD", "TND", "LYD",
                 "IQD", "CLP", "CLF", "UYW", "ISK", "HUF", "PYG", "UGX", "XAF", "XOF"]:
        add(c, code.lower(), f"ISO 4217 minor units of {code}", "minor_units", {"currency": code})
    for code, why in [("XAU", "gold: minor units N.A."), ("XXX", "the no-currency code"),
                      ("XTS", "the testing code"), ("XDR", "SDR: minor units N.A."), ("ABC", "not assigned")]:
        add(c, code.lower() + "-unknown", f"{code} ({why}) is not in the SDK table", "minor_units", {"currency": code})
    for slug, code, why in [("lower-case", "cny", "lower case"), ("two-letters", "CN", "two letters"),
                            ("four-letters", "CNYX", "four letters"), ("empty", "", "empty"),
                            ("numeric", "156", "the numeric code"), ("leading-space", " CNY", "leading space")]:
        add(c, "invalid-" + slug, f"{code!r} is not an alphabetic ISO code ({why})", "minor_units", {"currency": code})
    return c


def gen_parse():
    c = CaseList("money", "parse")
    for slug, s, kind in [
        ("plain", "12.30", "amount"), ("integer", "1230", "amount"), ("negative", "-5.25", "amount"),
        ("negative-zero", "-0", "amount"), ("negative-zero-fraction", "-0.000", "amount"),
        ("leading-zeros", "007.50", "amount"), ("zero", "0", "amount"),
        ("trailing-zeros-beyond-scale", "1.2300000000", "amount"),
        ("amount-max", "999999999999999.9999", "amount"), ("amount-min", "-999999999999999.9999", "amount"),
        ("price-six-decimals", "0.003500", "price"), ("price-max", "9999999999999.999999", "price"),
        ("cost", "12.345678", "cost"), ("quantity", "12.000001", "quantity"),
        ("rate-ten-decimals", "7.1234567891", "rate"), ("ratio", "0.130000", "ratio"),
        ("ratio-max", "999.999999", "ratio"), ("factor-small", "0.000001000000", "factor"),
        ("decimal-unbounded", "123456789012345678901234567890.123456789", "decimal"),
        ("amount-too-many-integer-digits", "1000000000000000", "amount"),
        ("amount-negative-overflow", "-1000000000000000.00", "amount"),
        ("amount-five-decimals", "1.00001", "amount"), ("price-seven-decimals", "0.0035001", "price"),
        ("price-overflow", "10000000000000", "price"), ("rate-eleven-decimals", "1.00000000001", "rate"),
        ("ratio-overflow", "1000", "ratio"), ("unknown-kind", "1", "percent"),
    ]:
        add(c, slug, f"parse {s!r} as {kind}", "parse", {"value": s, "kind": kind})
    for slug, s in [
        ("empty", ""), ("space-inside", "1 000"), ("leading-space", " 1"), ("trailing-space", "1 "),
        ("plus", "+1"), ("exponent", "1e5"), ("exponent-upper", "1E5"), ("exponent-fraction", "1.5e-3"),
        ("nan", "NaN"), ("nan-lower", "nan"), ("infinity", "Infinity"), ("negative-infinity", "-Infinity"),
        ("inf", "inf"), ("thousands-comma", "1,000.00"), ("decimal-comma", "12,30"),
        ("underscore", "1_000"), ("trailing-dot", "1."), ("leading-dot", ".5"), ("negative-dot", "-.5"),
        ("two-dots", "1.2.3"), ("double-minus", "--1"), ("minus-only", "-"), ("hex", "0x10"),
        ("fullwidth-digits", "１２"), ("arabic-indic-digits", "١٢"),
        ("currency-sign", "¥12"), ("currency-suffix", "12CNY"), ("newline", "12\n"),
    ]:
        add(c, slug, f"{s!r} is not a decimal string", "parse", {"value": s, "kind": "amount"})
    add(c, "json-number", "a JSON number is not a decimal string", "parse", {"value": 12.3, "kind": "amount"})
    add(c, "json-null", "null is not a decimal string", "parse", {"value": None, "kind": "amount"})
    return c


def gen_format():
    c = CaseList("money", "format")
    for slug, s, ccy in [
        ("cny", "12.3", "CNY"), ("cny-integer", "12", "CNY"), ("cny-exact", "12.30", "CNY"),
        ("jpy", "1230", "JPY"), ("jpy-zero-decimals", "1230.00", "JPY"), ("kwd", "1.234", "KWD"),
        ("kwd-pad", "1.2", "KWD"), ("clf-four", "0.0001", "CLF"), ("negative", "-0.5", "CNY"),
        ("negative-zero", "-0.00", "CNY"), ("zero-jpy", "0", "JPY"), ("large", "999999999999999.99", "USD"),
        ("cny-three-decimals", "12.345", "CNY"), ("jpy-decimals", "1230.5", "JPY"),
        ("kwd-four-decimals", "1.2345", "KWD"), ("bad-syntax", "1e3", "CNY"),
        ("unknown-currency", "1", "XYZ"), ("invalid-currency", "1", "cny"),
        ("overflow", "1000000000000000", "CNY"),
    ]:
        add(c, slug, f"format {s!r} in {ccy} (format never rounds)", "format", {"value": s, "currency": ccy})
    return c


def gen_round():
    c = CaseList("money", "round")
    for slug, s, ccy, mode in [
        ("cny-tie", "2.345", "CNY", HAE), ("cny-tie-even-down", "2.345", "CNY", HE),
        ("cny-tie-even-up", "2.355", "CNY", HE), ("cny-below-tie", "2.3449999", "CNY", HAE),
        ("cny-above-tie-even", "2.3450001", "CNY", HE), ("cny-negative-tie", "-2.345", "CNY", HAE),
        ("cny-negative-tie-even", "-2.345", "CNY", HE), ("cny-negative-to-zero", "-0.004", "CNY", HAE),
        ("cny-negative-tie-to-zero-even", "-0.005", "CNY", HE), ("cny-already-rounded", "2.30", "CNY", HAE),
        ("jpy-tie", "1230.5", "JPY", HAE), ("jpy-tie-even", "1230.5", "JPY", HE),
        ("jpy-tie-even-odd", "1231.5", "JPY", HE), ("kwd-tie", "1.2345", "KWD", HAE),
        ("kwd-tie-even", "1.2345", "KWD", HE), ("clf", "1.23455", "CLF", HAE),
        ("carry", "9.995", "CNY", HAE), ("carry-integer", "999999.5", "JPY", HAE),
        ("long-fraction", "0.1249999999999999999999999", "CNY", HAE),
        ("unknown-mode", "1.005", "CNY", "HALF_UP"), ("mode-lower-case", "1.005", "CNY", "half_even"),
        ("bad-value", "1,005", "CNY", HE), ("unknown-currency", "1.005", "XXX", HE),
    ]:
        add(c, slug, f"round {s!r} to the minor units of {ccy}, {mode}", "round",
            {"value": s, "currency": ccy, "mode": mode})
    add(c, "default-mode", "mode omitted means HALF_AWAY_FROM_ZERO", "round", {"value": "0.125", "currency": "CNY"})
    for slug, s, sc, mode in [
        ("scale-6-price", "0.00349951", 6, HAE), ("scale-10-rate", "7.12345678905", 10, HE),
        ("scale-0", "2.5", 0, HAE), ("scale-0-even", "2.5", 0, HE), ("scale-4", "-1.00005", 4, HAE),
    ]:
        add(c, slug, f"round {s} to scale {sc}, {mode}", "round", {"value": s, "scale": sc, "mode": mode})
    for slug, s, ccy, inc, mode in [
        ("chf-cash-up", "1.03", "CHF", "0.05", HAE), ("chf-cash-tie", "1.025", "CHF", "0.05", HAE),
        ("chf-cash-tie-even", "1.025", "CHF", "0.05", HE), ("chf-cash-down", "1.02", "CHF", "0.05", HAE),
        ("chf-cash-negative", "-1.075", "CHF", "0.05", HAE), ("cny-cash-jiao", "12.35", "CNY", "0.1", HAE),
        ("cash-increment-finer-than-currency", "1.0", "JPY", "0.5", HAE),
        ("cash-increment-zero", "1.0", "CHF", "0", HAE),
    ]:
        add(c, slug, f"cash rounding of {s} {ccy} to a multiple of {inc}, {mode}", "round_cash",
            {"value": s, "currency": ccy, "increment": inc, "mode": mode})
    for slug, s, step, mode in [
        ("qty-milli", "1.23456", "0.001", HAE), ("qty-milli-tie", "1.2345", "0.001", HAE),
        ("qty-milli-tie-even", "1.2345", "0.001", HE), ("qty-unit", "2.5", "1", HAE),
        ("qty-serial-integer", "3.0", "1", HAE), ("qty-half-step", "1.26", "0.5", HAE),
        ("qty-negative", "-1.2345", "0.01", HAE), ("qty-rounding-zero", "1", "0", HAE),
        ("qty-rounding-negative", "1", "-0.01", HAE),
    ]:
        add(c, slug, f"round quantity {s} by unit rounding {step}, {mode}", "round_qty",
            {"value": s, "rounding": step, "mode": mode})
    return c


def gen_allocate():
    c = CaseList("money", "allocate")
    for slug, total, ccy, ws, why in [
        ("thirds", "100.00", "CNY", ["1", "1", "1"], "the documented example"),
        ("thirds-jpy", "100", "JPY", ["1", "1", "1"], "no decimals"),
        ("by-amounts", "10.00", "CNY", ["30.00", "50.00", "20.00"], "weights are line amounts"),
        ("remainders-largest-first", "1.00", "CNY", ["1", "2", "4"], "largest remainders get the cents"),
        ("tie-earlier-line", "0.02", "CNY", ["1", "1", "1"], "equal remainders: earlier lines first"),
        ("single", "12.34", "CNY", ["5"], "one line takes everything"),
        ("zero-total", "0.00", "CNY", ["1", "2"], "nothing to allocate"),
        ("zero-weight-line", "10.00", "CNY", ["0", "1", "1"], "a zero weight gets zero"),
        ("negative-total", "-100.00", "CNY", ["1", "1", "1"], "a credit: allocate |total| then negate"),
        ("negative-small", "-0.01", "CNY", ["1", "1"], "one cent of credit"),
        ("kwd", "1.000", "KWD", ["1", "1", "1"], "three-decimal currency"),
        ("decimal-weights", "99.99", "USD", ["0.333", "0.333", "0.334"], "fractional weights"),
        ("seven-lines", "1.00", "CNY", ["1"] * 7, "1/7 each"),
        ("big", "999999999999999.99", "CNY", ["1", "2"], "the largest CNY amount"),
        ("cents-to-many", "0.05", "CNY", ["1"] * 10, "fewer cents than lines"),
        ("no-weights", "1.00", "CNY", [], "no lines"),
        ("all-zero", "1.00", "CNY", ["0", "0"], "weights sum to zero"),
        ("negative-weight", "1.00", "CNY", ["2", "-1"], "a negative weight"),
        ("total-too-fine", "1.005", "CNY", ["1", "1"], "total not at minor units"),
        ("bad-weight", "1.00", "CNY", ["1e2"], "a weight that is not a decimal string"),
    ]:
        add(c, slug, f"allocate {total} {ccy} by {ws}: {why}", "allocate",
            {"total": total, "currency": ccy, "weights": ws})
    exp = run("allocate", {"total": "100.00", "currency": "CNY", "weights": ["1", "1", "1"]})
    assert exp == {"parts": ["33.34", "33.33", "33.33"]}, exp  # foundations 06, Conformance tests
    return c


def gen_tax():
    c = CaseList("money", "tax")
    for slug, how, nets, rate, ccy, mode in [
        ("vat13-line", "line", ["10.01", "10.01", "10.01"], "0.13", "CNY", HAE),
        ("vat13-document", "document", ["10.01", "10.01", "10.01"], "0.13", "CNY", HAE),
        ("vat6-line", "line", ["0.05", "0.05", "0.05", "0.05"], "0.06", "CNY", HAE),
        ("vat6-document", "document", ["0.05", "0.05", "0.05", "0.05"], "0.06", "CNY", HAE),
        ("vat9-line", "line", ["0.50", "1.50"], "0.09", "CNY", HAE),
        ("vat9-line-even", "line", ["0.50", "1.50"], "0.09", "CNY", HE),
        ("zero-rate", "line", ["100.00"], "0", "CNY", HAE),
        ("jpy-document", "document", ["105", "205", "305"], "0.10", "JPY", HAE),
        ("jpy-line", "line", ["105", "205", "305"], "0.10", "JPY", HAE),
        ("rate-negative", "line", ["1.00"], "-0.13", "CNY", HAE),
        ("rate-above-one", "document", ["1.00"], "1.5", "CNY", HAE),
        ("document-negative-line", "document", ["10.00", "-2.00"], "0.13", "CNY", HAE),
        ("line-net-too-fine", "line", ["1.001"], "0.13", "CNY", HAE),
    ]:
        add(c, slug, f"tax per {how} at {rate} on {nets} {ccy}, {mode}", "tax_" + how,
            {"lines": nets, "rate": rate, "currency": ccy, "mode": mode})
    return c


def gen_arith():
    c = CaseList("money", "arithmetic")
    A = lambda v, k: {"value": v, "currency": k}  # noqa: E731
    for slug, op, a, b in [
        ("add-same", "add", A("12.30", "CNY"), A("0.70", "CNY")),
        ("sub-same", "sub", A("12.30", "CNY"), A("20.00", "CNY")),
        ("add-jpy", "add", A("100", "JPY"), A("23", "JPY")),
        ("add-mismatch", "add", A("1.00", "CNY"), A("1.00", "USD")),
        ("sub-mismatch", "sub", A("1", "JPY"), A("1.00", "CNY")),
        ("add-overflow", "add", A("999999999999999.99", "CNY"), A("0.01", "CNY")),
        ("add-too-fine", "add", A("1.001", "CNY"), A("1", "CNY")),
    ]:
        add(c, slug, f"{op} {a} and {b}", op, {"a": a, "b": b})
    for slug, v, f, rate, t, mode in [
        ("usd-to-cny", "100.00", "USD", "7.1234567891", "CNY", HAE),
        ("jpy-to-cny", "12345", "JPY", "0.0478123456", "CNY", HAE),
        ("cny-to-jpy-tie", "10.00", "CNY", "20.05", "JPY", HAE),
        ("cny-to-jpy-tie-even", "10.00", "CNY", "20.05", "JPY", HE),
        ("cny-to-kwd", "1000.00", "CNY", "0.0428765432", "KWD", HAE),
        ("negative", "-100.00", "USD", "7.12345", "CNY", HAE),
        ("same-currency", "12.34", "CNY", "1", "CNY", HAE),
        ("rate-zero", "1.00", "USD", "0", "CNY", HE), ("rate-negative", "1.00", "USD", "-7.1", "CNY", HE),
        ("rate-too-fine", "1.00", "USD", "7.12345678901", "CNY", HE),
        ("same-currency-rate", "1.00", "CNY", "1.1", "CNY", HE),
    ]:
        add(c, slug, f"convert {v} {f} at {rate} to {t}, {mode}", "convert",
            {"amount": A(v, f), "rate": rate, "to": t, "mode": mode})
    for slug, q, p, d, ccy, mode in [
        ("simple", "3", "19.99", "0", "CNY", HAE), ("fine-price", "1000", "0.0035", "0", "CNY", HAE),
        ("fine-price-tie", "1", "0.005", "0", "CNY", HAE), ("fine-price-tie-even", "1", "0.005", "0", "CNY", HE),
        ("discount", "3", "19.99", "0.15", "CNY", HAE), ("fractional-qty", "2.5", "3.333333", "0.1", "CNY", HAE),
        ("jpy", "7", "123.4567", "0.05", "JPY", HAE), ("negative-qty-return", "-2", "10.005", "0", "CNY", HAE),
        ("full-discount", "5", "10", "1", "CNY", HAE), ("discount-negative", "1", "1", "-0.1", "CNY", HE),
        ("discount-above-one", "1", "1", "1.01", "CNY", HE), ("price-too-fine", "1", "0.0000001", "0", "CNY", HE),
        ("overflow", "9999999999999", "9999999999999", "0", "CNY", HE),
    ]:
        add(c, "line-" + slug, f"line amount {q} x {p} less {d} in {ccy}, {mode}, rounded once", "line_amount",
            {"quantity": q, "price": p, "discount": d, "currency": ccy, "mode": mode})
    return c


def main():
    import json
    counts = {}
    for topic, fn in [("columns", gen_columns), ("currencies", gen_currencies), ("parse", gen_parse),
                      ("format", gen_format), ("round", gen_round), ("allocate", gen_allocate),
                      ("tax", gen_tax), ("arithmetic", gen_arith)]:
        counts[topic] = write_file(os.path.join(OUT, f"{topic}.json"), "money", topic, GEN, fn())
    with open(os.path.join(OUT, "iso4217.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"source": "ISO 4217 List One (SIX Financial Information)", "published": PUBLISHED,
                   "generated_by": GEN,
                   "note": "The table every official SDK embeds. Codes whose minor units are N.A. "
                           "(precious metals, SDR, XSU, XUA, XXX, XTS) are absent on purpose.",
                   "minor_units": dict(sorted(ISO.items()))}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("money", counts, "total", sum(counts.values()), "| iso4217 codes:", len(ISO))


if __name__ == "__main__":
    main()
