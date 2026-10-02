#!/usr/bin/env python3
"""Generate vectors/calendar/*.json (protocol P11.7, P11.9; foundations 05).

Business date = the civil date of an instant in the legal entity's IANA time
zone. Day bounds = the half-open instant range [first instant of the day,
first instant of the next day). Fiscal periods are month-based with a
configurable start month. Reference: Python zoneinfo over the system tz
database; xcheck_calendar.mjs recomputes everything with Node's Intl (ICU).
"""

import calendar as pycal
import datetime as dt
import os
import re
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_lib"))
from vecfile import CaseList, area_dir, write_file  # noqa: E402

GEN = "calendar/gen/gen_calendar.py"
OUT = area_dir(__file__)
UTC = dt.timezone.utc
ZONE_RE = re.compile(r"UTC|[A-Z][A-Za-z_]+(/[A-Z0-9][A-Za-z0-9_+-]*)+")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
INSTANT_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z")


class CalError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def tzdata_version():
    try:
        with open("/usr/share/zoneinfo/tzdata.zi") as f:
            return f.readline().split()[-1]
    except OSError:
        return "unknown"


def zone(name):
    if not isinstance(name, str) or not ZONE_RE.fullmatch(name):
        raise CalError("TZ_UNKNOWN")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise CalError("TZ_UNKNOWN")


def parse_date(s):
    if not isinstance(s, str) or not DATE_RE.fullmatch(s):
        raise CalError("DATE_INVALID")
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        raise CalError("DATE_INVALID")


def parse_instant(s):
    if not isinstance(s, str) or not INSTANT_RE.fullmatch(s):
        raise CalError("INSTANT_INVALID")
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def fmt_instant(t):
    t = t.astimezone(UTC)
    s = t.strftime("%Y-%m-%dT%H:%M:%S")
    if t.microsecond:
        s += "." + f"{t.microsecond:06d}".rstrip("0")
    return s + "Z"


def business_date(instant, zname):
    return parse_instant(instant).astimezone(zone(zname)).date()


def day_start(d, z):
    """First instant whose civil date in z is >= d (second resolution)."""
    lo = int(dt.datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp()) - 20 * 3600
    hi = lo + 48 * 3600
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if dt.datetime.fromtimestamp(mid, z).date() >= d:
            hi = mid
        else:
            lo = mid
    return dt.datetime.fromtimestamp(hi, UTC)


def day_bounds(date_s, zname):
    d = parse_date(date_s)
    z = zone(zname)
    start = day_start(d, z)
    if start.astimezone(z).date() != d:
        raise CalError("DATE_NONEXISTENT")  # the civil date was skipped in this zone
    end = day_start(d + dt.timedelta(days=1), z)
    return {"start": fmt_instant(start), "end": fmt_instant(end),
            "hours": (end - start).total_seconds() / 3600}


def date_range(first, last, zname):
    a, b = parse_date(first), parse_date(last)
    if b < a:
        raise CalError("RANGE_INVALID")
    z = zone(zname)
    start = day_start(a, z)
    end = day_start(b + dt.timedelta(days=1), z)
    return {"start": fmt_instant(start), "end": fmt_instant(end)}


def period_of(d, s):
    if not isinstance(s, int) or isinstance(s, bool) or not 1 <= s <= 12:
        raise CalError("FISCAL_START_INVALID")
    fy = d.year if d.month >= s else d.year - 1
    p = (d.month - s) % 12 + 1
    last = pycal.monthrange(d.year, d.month)[1]
    return {
        "fiscal_year": fy,
        "fiscal_year_label": str(fy) if s == 1 else f"{fy}/{(fy + 1) % 100:02d}",
        "period": p,
        "period_key": f"{fy}-P{p:02d}",
        "start_date": dt.date(d.year, d.month, 1).isoformat(),
        "end_date": dt.date(d.year, d.month, last).isoformat(),
        "label": f"{d.year:04d}-{d.month:02d}",
    }


def fiscal_year(fy, s):
    if not isinstance(s, int) or not 1 <= s <= 12:
        raise CalError("FISCAL_START_INVALID")
    out = []
    y, m = fy, s
    for _ in range(12):
        pr = period_of(dt.date(y, m, 1), s)
        out.append({k: pr[k] for k in ("period", "period_key", "start_date", "end_date", "label")})
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return {"fiscal_year": fy, "start_date": out[0]["start_date"], "end_date": out[-1]["end_date"], "periods": out}


def add(c, slug, why, op, inp, refs=("P11.7",)):
    try:
        if op == "business_date":
            exp = {"date": business_date(inp["instant"], inp["time_zone"]).isoformat()}
        elif op == "day_bounds":
            exp = day_bounds(inp["date"], inp["time_zone"])
        elif op == "date_range":
            exp = date_range(inp["first"], inp["last"], inp["time_zone"])
        elif op == "fiscal_period":
            exp = period_of(parse_date(inp["date"]), inp["start_month"])
        elif op == "fiscal_year":
            exp = fiscal_year(inp["fiscal_year"], inp["start_month"])
        elif op == "parse_date":
            exp = {"date": parse_date(inp["value"]).isoformat()}
        else:
            raise KeyError(op)
        c.add(slug, why, op, inp, expected=exp, refs=list(refs))
    except CalError as e:
        c.add(slug, why, op, inp, error=e.reason, refs=list(refs))


def gen_business_date():
    c = CaseList("calendar", "business_date")
    rows = [
        # Asia/Shanghai, the default zone: UTC 16:00 is the next day's midnight
        ("shanghai-midnight", "2026-09-30T16:00:00Z", "Asia/Shanghai", "midnight in Beijing on 1 October"),
        ("shanghai-before-midnight", "2026-09-30T15:59:59.999999Z", "Asia/Shanghai", "the last microsecond of 30 September"),
        ("shanghai-0730", "2026-09-30T23:30:00Z", "Asia/Shanghai", "07:30 Beijing on 1 October is still 30 September in UTC"),
        ("shanghai-month-end-afternoon", "2026-10-31T07:00:00Z", "Asia/Shanghai", "the afternoon of the last day of the month"),
        ("shanghai-year-end", "2026-12-31T16:00:00Z", "Asia/Shanghai", "the new year starts at 16:00 UTC"),
        ("utc-same-instant", "2026-09-30T16:00:00Z", "UTC", "the same instant is still 30 September in UTC"),
        # one instant, two legal entities in different zones
        ("two-entities-shanghai", "2026-10-01T02:00:00Z", "Asia/Shanghai", "10:00 in Beijing"),
        ("two-entities-new-york", "2026-10-01T02:00:00Z", "America/New_York", "22:00 the evening before in New York"),
        # America/New_York, DST 2026-03-08 and 2026-11-01
        ("ny-spring-before", "2026-03-08T04:59:59Z", "America/New_York", "23:59:59 EST on 7 March"),
        ("ny-spring-midnight", "2026-03-08T05:00:00Z", "America/New_York", "00:00 EST on 8 March"),
        ("ny-spring-gap", "2026-03-08T07:00:00Z", "America/New_York", "02:00 EST becomes 03:00 EDT"),
        ("ny-spring-next-before", "2026-03-09T03:59:59Z", "America/New_York", "23:59:59 EDT on 8 March"),
        ("ny-spring-next-midnight", "2026-03-09T04:00:00Z", "America/New_York", "00:00 EDT on 9 March"),
        ("ny-fall-before", "2026-11-01T03:59:59Z", "America/New_York", "23:59:59 EDT on 31 October"),
        ("ny-fall-midnight", "2026-11-01T04:00:00Z", "America/New_York", "00:00 EDT on 1 November"),
        ("ny-fall-repeated-hour", "2026-11-01T06:30:00Z", "America/New_York", "01:30 EST, the second 01:30"),
        ("ny-fall-next-before", "2026-11-02T04:59:59Z", "America/New_York", "23:59:59 EST on 1 November"),
        ("ny-fall-next-midnight", "2026-11-02T05:00:00Z", "America/New_York", "00:00 EST on 2 November"),
        # Europe/London
        ("london-winter", "2026-01-15T00:00:00Z", "Europe/London", "GMT"),
        ("london-summer-midnight", "2026-07-14T23:00:00Z", "Europe/London", "00:00 BST is 23:00 UTC"),
        ("london-summer-before", "2026-07-14T22:59:59Z", "Europe/London", "23:59:59 BST"),
        # southern hemisphere
        ("sydney-summer", "2026-01-15T13:00:00Z", "Australia/Sydney", "AEDT +11: 00:00 on 16 January"),
        ("sydney-winter", "2026-07-15T14:00:00Z", "Australia/Sydney", "AEST +10: 00:00 on 16 July"),
        ("sydney-dst-end-day", "2026-04-04T13:00:00Z", "Australia/Sydney", "00:00 AEDT on 5 April, the DST end day"),
        # unusual offsets
        ("kolkata-half-hour", "2026-10-01T18:30:00Z", "Asia/Kolkata", "+05:30 midnight"),
        ("kolkata-half-hour-before", "2026-10-01T18:29:59Z", "Asia/Kolkata", "+05:30, one second earlier"),
        ("kathmandu-45", "2026-10-01T18:15:00Z", "Asia/Kathmandu", "+05:45 midnight"),
        ("chatham-1345", "2026-01-01T10:15:00Z", "Pacific/Chatham", "+13:45 in the southern summer"),
        ("kiritimati-plus-14", "2026-10-01T10:00:00Z", "Pacific/Kiritimati", "+14: already the next day"),
        ("pago-pago-minus-11", "2026-10-01T10:59:59Z", "Pacific/Pago_Pago", "-11: still the previous day"),
        ("st-johns-half-hour", "2026-07-01T02:30:00Z", "America/St_Johns", "NDT -02:30 midnight"),
        ("etc-gmt-minus-8", "2026-09-30T16:00:00Z", "Etc/GMT-8", "Etc/GMT-8 is UTC+8 (POSIX sign inverted)"),
        ("etc-gmt-plus-8", "2026-10-01T07:59:59Z", "Etc/GMT+8", "Etc/GMT+8 is UTC-8"),
        # history
        ("apia-before-skip", "2011-12-30T09:59:59Z", "Pacific/Apia", "23:59:59 on 29 December 2011 at UTC-10"),
        ("apia-after-skip", "2011-12-30T10:00:00Z", "Pacific/Apia", "30 December 2011 was skipped: 00:00 on the 31st at UTC+14"),
        ("sao-paulo-midnight-dst", "2018-11-04T03:00:00Z", "America/Sao_Paulo", "DST began at midnight: 00:00 did not exist, 01:00 -02"),
        ("sao-paulo-before-midnight-dst", "2018-11-04T02:59:59Z", "America/Sao_Paulo", "23:59:59 -03 on 3 November"),
        ("leap-day", "2028-02-28T16:00:00Z", "Asia/Shanghai", "29 February 2028"),
        # rejected input
        ("zone-unknown", "2026-10-01T00:00:00Z", "Asia/Beijing", "not an IANA zone"),
        ("zone-offset-string", "2026-10-01T00:00:00Z", "+08:00", "an offset is not a zone"),
        ("zone-utc-plus", "2026-10-01T00:00:00Z", "UTC+8", "not an IANA zone"),
        ("zone-lower-case", "2026-10-01T00:00:00Z", "asia/shanghai", "zone names are case-sensitive"),
        ("zone-empty", "2026-10-01T00:00:00Z", "", "empty"),
        ("instant-offset", "2026-10-01T08:00:00+08:00", "Asia/Shanghai", "instants travel in UTC with Z"),
        ("instant-no-zone", "2026-10-01T08:00:00", "Asia/Shanghai", "a local time is not an instant"),
        ("instant-date-only", "2026-10-01", "Asia/Shanghai", "a date is not an instant"),
    ]
    for slug, inst, z, why in rows:
        add(c, slug, why, "business_date", {"instant": inst, "time_zone": z})
    return c


def gen_bounds():
    c = CaseList("calendar", "bounds")
    for slug, d, z, why in [
        ("shanghai", "2026-10-01", "Asia/Shanghai", "a 24-hour day"),
        ("utc", "2026-10-01", "UTC", "UTC"),
        ("ny-spring", "2026-03-08", "America/New_York", "a 23-hour day"),
        ("ny-fall", "2026-11-01", "America/New_York", "a 25-hour day"),
        ("london-spring", "2026-03-29", "Europe/London", "BST begins"),
        ("sydney-autumn", "2026-04-05", "Australia/Sydney", "a 25-hour day in April"),
        ("sydney-spring", "2026-10-04", "Australia/Sydney", "a 23-hour day in October"),
        ("chatham", "2026-04-05", "Pacific/Chatham", "Chatham DST ends at 03:45"),
        ("sao-paulo-start-not-midnight", "2018-11-04", "America/Sao_Paulo", "the day starts at 01:00 because 00:00 was skipped"),
        ("sao-paulo-two-midnights", "2019-02-16", "America/Sao_Paulo", "23:00-24:00 happens twice: a 25-hour day"),
        ("apia-skipped-day", "2011-12-30", "Pacific/Apia", "the day does not exist in Apia"),
        ("apia-day-after", "2011-12-31", "Pacific/Apia", "the first day after the skip"),
        ("bad-date", "2026-02-30", "Asia/Shanghai", "no such date"),
        ("bad-zone", "2026-10-01", "Mars/Olympus", "no such zone"),
    ]:
        add(c, slug, why, "day_bounds", {"date": d, "time_zone": z})
    for slug, a, b, z, why in [
        ("month-shanghai", "2026-10-01", "2026-10-31", "Asia/Shanghai", "October in Beijing"),
        ("month-ny-dst", "2026-11-01", "2026-11-30", "America/New_York", "November across the DST end"),
        ("one-day", "2026-10-01", "2026-10-01", "Asia/Shanghai", "a single day"),
        ("fiscal-year-april", "2026-04-01", "2027-03-31", "Asia/Shanghai", "an April-start fiscal year"),
        ("reversed", "2026-10-31", "2026-10-01", "Asia/Shanghai", "last before first"),
    ]:
        add(c, "range-" + slug, why, "date_range", {"first": a, "last": b, "time_zone": z})
    for slug, v, why in [
        ("ok", "2026-10-02", "a business date"), ("leap", "2028-02-29", "a leap day"),
        ("not-leap", "2026-02-29", "2026 is not a leap year"), ("short-month", "2026-10-2", "one-digit day"),
        ("datetime", "2026-10-02T00:00:00Z", "an instant at midnight is not a business date"),
        ("slashes", "2026/10/02", "slashes"), ("month-13", "2026-13-01", "month 13"),
        ("expanded-year", "+002026-10-02", "expanded year"), ("empty", "", "empty"),
        ("compact", "20261002", "basic format"),
    ]:
        add(c, "parse-" + slug, why, "parse_date", {"value": v})
    return c


def gen_fiscal():
    c = CaseList("calendar", "fiscal")
    for slug, d, s, why in [
        ("jan-start", "2026-10-15", 1, "calendar fiscal year"),
        ("jan-start-january", "2026-01-01", 1, "first period"),
        ("jan-start-december", "2026-12-31", 1, "last period"),
        ("april-start-april", "2026-04-01", 4, "first period of FY 2026/27"),
        ("april-start-march", "2027-03-31", 4, "last period of FY 2026/27"),
        ("april-start-october", "2026-10-02", 4, "period 7; the label 2026-10 is display only"),
        ("april-start-january", "2027-01-15", 4, "January belongs to the fiscal year that began the April before"),
        ("july-start", "2026-06-30", 7, "June is the last period of FY 2025/26"),
        ("october-start", "2026-10-01", 10, "first period of FY 2026/27"),
        ("december-start", "2026-11-30", 12, "December start: November is period 12"),
        ("leap-february", "2028-02-29", 4, "the leap day"),
        ("start-zero", "2026-10-01", 0, "start month 0"),
        ("start-thirteen", "2026-10-01", 13, "start month 13"),
        ("bad-date", "2026-02-29", 1, "no such date"),
    ]:
        add(c, slug, why, "fiscal_period", {"date": d, "start_month": s}, refs=("P11.7", "P11.9"))
    for slug, fy, s, why in [
        ("year-jan", 2026, 1, "twelve calendar months"),
        ("year-april", 2026, 4, "April 2026 to March 2027"),
        ("year-march-leap", 2027, 3, "March 2027 to February 2028 (leap)"),
        ("year-bad-start", 2026, 0, "start month 0"),
    ]:
        add(c, slug, why, "fiscal_year", {"fiscal_year": fy, "start_month": s}, refs=("P11.7", "P11.9"))
    return c


def main():
    counts = {}
    notes = {"tzdata": tzdata_version()}
    for topic, fn in [("business_date", gen_business_date), ("bounds", gen_bounds), ("fiscal", gen_fiscal)]:
        counts[topic] = write_file(os.path.join(OUT, f"{topic}.json"), "calendar", topic, GEN, fn(), notes=notes)
    print("calendar", counts, "total", sum(counts.values()), "tzdata", notes["tzdata"])


if __name__ == "__main__":
    main()
