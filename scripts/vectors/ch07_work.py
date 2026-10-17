"""Chapter 07: cron slots and materialization (P7.15, P7.16)."""
from common import write


# ---------------------------------------------------------------- cron slots (P7.15, P7.16)
def cron_field(spec, lo, hi):
    out = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, st = part.split("/")
            step = int(st)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = map(int, part.split("-"))
        else:
            a = b = int(part)
            if step != 1:
                b = hi
        out.update(range(a, b + 1, step))
    return out


def cron_parse(expr):
    f = expr.split()
    assert len(f) == 5, expr
    dow = {d % 7 for d in cron_field(f[4], 0, 7)}
    return (cron_field(f[0], 0, 59), cron_field(f[1], 0, 23), cron_field(f[2], 1, 31), cron_field(f[3], 1, 12), dow,
            f[2] != "*", f[4] != "*")


def wall_instant(wall, tz):
    """The run instant of a local wall time: the first occurrence; in a gap, the first instant after the jump."""
    from datetime import timezone as _tz, timedelta as _td
    utc = _tz.utc
    cands = []
    for fold in (0, 1):
        t = wall.replace(tzinfo=tz, fold=fold).astimezone(utc)
        if t.astimezone(tz).replace(tzinfo=None) == wall:
            cands.append(t)
    if cands:
        return min(cands)
    lo = (wall - _td(hours=15)).replace(tzinfo=utc)
    hi = (wall + _td(hours=15)).replace(tzinfo=utc)
    while (hi - lo).total_seconds() > 1:
        mid = lo + (hi - lo) / 2
        if mid.astimezone(tz).replace(tzinfo=None) >= wall:
            hi = mid
        else:
            lo = mid
    return hi.replace(microsecond=0)


def cron_slots(expr, tzname, start, end):
    """Slots whose run instant is in (start, end], in order."""
    from datetime import datetime as _dt, timedelta as _td
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tzname)
    mins, hours, doms, months, dows, dom_r, dow_r = cron_parse(expr)
    out = []
    d = (start.astimezone(tz) - _td(days=1)).date()
    last = (end.astimezone(tz) + _td(days=1)).date()
    while d <= last:
        dow = (d.weekday() + 1) % 7
        if dom_r and dow_r:
            day_ok = d.day in doms or dow in dows
        else:
            day_ok = d.day in doms and dow in dows
        if d.month in months and day_ok:
            for h in sorted(hours):
                for m in sorted(mins):
                    wall = _dt(d.year, d.month, d.day, h, m)
                    at = wall_instant(wall, tz)
                    if start < at <= end:
                        out.append((at, wall.strftime("%Y-%m-%dT%H:%M")))
        d += _td(days=1)
    out.sort()
    return out


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def cron_vectors():
    from datetime import datetime as _dt, timezone as _tz
    U = lambda *a: _dt(*a, tzinfo=_tz.utc)
    scen = [
        ("daily-0230-berlin-spring-forward", "30 2 * * *", "Europe/Berlin", U(2026, 3, 27), U(2026, 3, 31)),
        ("daily-0230-berlin-fall-back", "30 2 * * *", "Europe/Berlin", U(2026, 10, 23), U(2026, 10, 27)),
        ("hourly-berlin-fall-back", "0 * * * *", "Europe/Berlin", U(2026, 10, 24, 22), U(2026, 10, 25, 4)),
        ("every-15-new-york-spring-forward", "*/15 1-3 * * *", "America/New_York", U(2026, 3, 8, 5), U(2026, 3, 8, 8)),
        ("daily-0130-new-york-fall-back", "30 1 * * *", "America/New_York", U(2026, 10, 31), U(2026, 11, 3)),
        ("weekdays-0900-shanghai", "0 9 * * 1-5", "Asia/Shanghai", U(2026, 10, 16), U(2026, 10, 23)),
        ("first-of-month-utc", "0 3 1 * *", "UTC", U(2026, 10, 15), U(2026, 12, 15)),
        ("dom-or-dow", "0 12 13 * 5", "UTC", U(2026, 11, 1), U(2026, 12, 1)),
        ("lists-and-steps", "5,35 */6 * * *", "UTC", U(2026, 10, 17), U(2026, 10, 18)),
        ("sunday-as-7", "0 8 * * 7", "UTC", U(2026, 10, 1), U(2026, 10, 15)),
        ("end-is-inclusive-start-exclusive", "0 0 * * *", "UTC", U(2026, 10, 17), U(2026, 10, 19)),
    ]
    cases = []
    for name, expr, tz, a, b in scen:
        cases.append({"id": name, "kind": "slots", "cron": expr, "tz": tz, "after": iso(a), "until": iso(b),
                      "expect": [{"slot": s, "at": iso(t)} for t, s in cron_slots(expr, tz, a, b)]})
    # materialization after a stop: the due slots between the watermark and now, by backfill policy
    for name, policy, hours_down in [("latest-after-5h", "latest", 5), ("none-after-5h", "none", 5),
                                     ("all-after-5h", "all", 5), ("all-after-30h-over-backlog", "all", 30),
                                     ("latest-nothing-missed", "latest", 0)]:
        wm = U(2026, 10, 17, 6, 0, 30)
        now = U(2026, 10, 17, 6 + hours_down % 18, 0, 30) if hours_down < 18 else U(2026, 10, 18, 12, 0, 30)
        if hours_down == 0:
            now = U(2026, 10, 17, 6, 30, 0)
        due = cron_slots("0 * * * *", "UTC", wm, now)
        if policy == "latest":
            run, paused = due[-1:], []
        elif policy == "none":
            run, paused = [x for x in due if (now - x[0]).total_seconds() <= 60], []
        else:
            run, paused = due[:24], due[24:]
        cases.append({"id": name, "kind": "materialize", "cron": "0 * * * *", "tz": "UTC", "policy": policy,
                      "max_backlog": 24, "watermark": iso(wm), "now": iso(now),
                      "expect": {"pending": [s for _, s in run], "paused": [s for _, s in paused],
                                 "watermark": iso(due[-1][0]) if due else iso(wm)}})
    write("cron-slots", ["P7.15", "P7.16"],
          "kind=slots：5 字段计划在时区中，运行时刻落在 (after, until] 的时间槽，按时刻排序；slot 是本地日期与本地时刻，at 是运行时刻（UTC）。"
          "夏令时开始跳过的本地时刻在跳变后的第一个时刻运行，身份不变；出现两次的本地时刻只在第一次运行。日与星期都有限制时，二者满足其一即可（cron 的惯例）。"
          "kind=materialize：停机后从物化水位到 now 之间到期的槽，按补跑策略物化：latest 只补最近一个；none 只物化 60 秒内到期的；"
          "all 按时刻先后物化前 max_backlog 个为 pending，其余为 paused（backlog_exceeded）。新水位是最后一个到期槽的运行时刻（没有到期槽时不变）。"
          "期望值由 gen-vectors.py 用 zoneinfo 计算；SDK 是第二个独立实现。",
          cases, {"cron": "5 字段计划", "tz": "IANA 时区", "after、until": "区间", "expect": "时间槽与运行时刻",
                  "policy": "补跑策略", "watermark、now": "物化水位与当前时刻"})
