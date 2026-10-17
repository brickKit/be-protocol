"""Chapter 05: amounts (parse, round, cash rounding, allocate, format) and business dates (P5.25-P5.29)."""
import re
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal, localcontext
from zoneinfo import ZoneInfo

from common import write

DECIMAL = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")
MODES = {"half_away_from_zero": ROUND_HALF_UP, "half_even": ROUND_HALF_EVEN}  # Python's HALF_UP is away from zero
CTX = Context(prec=60)


def parse(s, scale):
    if not DECIMAL.match(s) or len(s.replace("-", "").replace(".", "")) > 38:
        return None
    d = Decimal(s)
    if s == "-0" or (d == 0 and s.startswith("-")):
        return None
    if -d.normalize(CTX).as_tuple().exponent > scale and d != 0:
        return None
    return d


def fmt(d, scale):
    q = d.quantize(Decimal(1).scaleb(-scale), context=CTX)
    if q == 0:
        q = abs(q)
    return f"{q:f}"


def round_to(d, scale, mode):
    with localcontext(CTX):
        return d.quantize(Decimal(1).scaleb(-scale), rounding=MODES[mode])


def round_cash(d, unit, scale, mode):
    with localcontext(CTX):
        return round_to((d / unit).quantize(Decimal(1), rounding=MODES[mode]) * unit, scale, mode)


def allocate(total, weights, scale):
    with localcontext(CTX):
        unit = Decimal(1).scaleb(-scale)
        sign = -1 if total < 0 else 1
        units = int((abs(total) / unit).to_integral_value(rounding=ROUND_DOWN))
        wsum = sum(weights)
        shares = [Decimal(units) * w / wsum for w in weights]
        base = [int(s.to_integral_value(rounding=ROUND_DOWN)) for s in shares]
        left = units - sum(base)
        order = sorted(range(len(weights)), key=lambda i: (-(shares[i] - base[i]), i))
        for i in order[:left]:
            base[i] += 1
        return [fmt(Decimal(sign * b) * unit, scale) for b in base]


def money_vectors():
    cases = []
    for i, (s, scale) in enumerate([("12.30", 2), ("12.3", 2), ("12", 2), ("12.345", 2), ("12.340", 2), ("-0.01", 2),
                                    ("1e2", 2), ("+1", 2), ("01.5", 2), ("1.", 2), (".5", 2), ("", 2), ("-0", 2),
                                    ("0.000", 0), ("12.5", 0), ("9" * 15 + ".9999", 4), ("1" * 39, 0), ("100", 3),
                                    ("1 000", 2), ("١٢", 2)]):
        d = parse(s, scale)
        cases.append({"id": f"parse-{i:02d}", "kind": "parse", "value": s, "scale": scale,
                      "valid": d is not None, **({"formatted": fmt(d, scale)} if d is not None else {})})
    rounding = [("2.345", 2), ("2.355", 2), ("-2.345", 2), ("-2.355", 2), ("2.3449999", 2), ("0.005", 2),
                ("-0.005", 2), ("1.0005", 3), ("12.5", 0), ("13.5", 0), ("-12.5", 0), ("0.125", 2), ("7", 2),
                ("123456789012345.67895", 4)]
    for i, (v, scale) in enumerate(rounding):
        for mode in MODES:
            cases.append({"id": f"round-{i:02d}-{mode}", "kind": "round", "value": v, "scale": scale, "mode": mode,
                          "result": fmt(round_to(Decimal(v), scale, mode), scale)})
    for i, (v, unit, scale) in enumerate([("1.02", "0.05", 2), ("1.025", "0.05", 2), ("1.075", "0.05", 2),
                                          ("1.12", "0.05", 2), ("-1.025", "0.05", 2), ("12.49", "0.10", 2),
                                          ("12.50", "1", 2), ("12.34", "0.25", 2)]):
        for mode in MODES:
            cases.append({"id": f"cash-{i:02d}-{mode}", "kind": "cash", "value": v, "unit": unit, "scale": scale,
                          "mode": mode, "result": fmt(round_cash(Decimal(v), Decimal(unit), scale, mode), scale)})
    for i, (total, weights, scale) in enumerate([
            ("100.00", ["1", "1", "1"], 2), ("100.00", ["1", "2", "3"], 2), ("-100.00", ["1", "1", "1"], 2),
            ("0.05", ["1", "1", "1", "1"], 2), ("10.000", ["0.3", "0.3", "0.4"], 3), ("1", ["1", "1", "1"], 0),
            ("99.99", ["2", "0", "1"], 2), ("0.00", ["1", "1"], 2), ("1000", ["1"], 0),
            ("12.34", ["1.5", "1.5", "1"], 2)]):
        cases.append({"id": f"allocate-{i:02d}", "kind": "allocate", "total": total, "weights": weights,
                      "scale": scale, "parts": allocate(Decimal(total), [Decimal(w) for w in weights], scale)})
    write("money", ["P5.25", "P5.26", "P5.27", "P5.28"],
          "金额与十进制。kind=parse：契约中的十进制字符串在币种小数位 scale 下是否合格（-?整数部分[.小数部分]，整数部分无前导零，"
          "最多 38 位数字，不接受指数、正号、空格与非 ASCII 数字，不接受 -0；小数位多于 scale 且多出的不全是 0 时不合格），"
          "合格时 formatted 是按 scale 格式化的结果。kind=round：按 mode 舍入到 scale 位（half_away_from_zero 为四舍五入远离零，"
          "half_even 为银行家舍入）。kind=cash：先按 mode 舍入到 unit 的整数倍，再格式化到 scale 位。kind=allocate：最大余数法，"
          "按 weights 把 total 分成若干份，每份是最小单位（10^-scale）的整数倍，余下的最小单位依次给余数最大的份，余数相同给前面的；"
          "负数按绝对值分配后取负；各份之和恰好等于 total。全部数值以字符串表示，不经过浮点。",
          cases, {"value": "输入的十进制字符串", "scale": "小数位", "mode": "舍入方式", "unit": "现金舍入单位",
                  "result": "舍入后按 scale 格式化", "parts": "分摊结果，按 scale 格式化"})


def business_date_vectors():
    cases = []
    for i, (instant, tz) in enumerate([
            ("2026-10-17T23:30:00Z", "Europe/Madrid"), ("2026-10-17T21:59:59Z", "Europe/Madrid"),
            ("2026-10-17T22:00:00Z", "Europe/Madrid"), ("2026-10-17T15:59:59Z", "Asia/Shanghai"),
            ("2026-10-17T16:00:00Z", "Asia/Shanghai"), ("2026-03-08T07:30:00Z", "America/New_York"),
            ("2026-11-01T04:30:00Z", "America/New_York"), ("2026-11-01T05:30:00Z", "America/New_York"),
            ("2026-12-31T10:00:00Z", "Pacific/Kiritimati"), ("2026-01-01T10:59:59Z", "Pacific/Pago_Pago"),
            ("2026-06-30T23:59:59Z", "UTC"), ("2026-03-29T00:59:59Z", "Europe/Madrid")]):
        at = datetime.fromisoformat(instant.replace("Z", "+00:00"))
        cases.append({"id": f"date-{i:02d}", "instant": instant, "tz": tz,
                      "date": at.astimezone(ZoneInfo(tz)).date().isoformat()})
    write("business-date", ["P5.29"],
          "业务日期：时刻 instant（UTC）在法人的 IANA 时区 tz 中的本地日期（YYYY-MM-DD）；“今天”就是当前时刻的业务日期。"
          "期望值由 zoneinfo 计算。",
          cases, {"instant": "UTC 时刻", "tz": "法人时区", "date": "业务日期"})
