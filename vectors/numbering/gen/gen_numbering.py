#!/usr/bin/env python3
"""Generate vectors/numbering/*.json (protocol P11.10; foundations 04).

Document number formats (`<NAME>_NO_FORMAT`), the period key a format resets
on, and the allocation model of gap-free and gapped series.
xcheck_numbering.mjs recomputes every case in Node.
"""

import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_lib"))
from vecfile import CaseList, area_dir, write_file  # noqa: E402

GEN = "numbering/gen/gen_numbering.py"
OUT = area_dir(__file__)
TOKEN = re.compile(r"\{([^{}]*)\}")
SEQ = re.compile(r"seq:([0-9]{1,2})")  # width N, written N or 0N (printf style): 5 or 05


class NumError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def compile_format(f):
    """Split a format into literal and placeholder parts, validating it."""
    if not isinstance(f, str) or not f:
        raise NumError("FORMAT_INVALID")
    parts, pos, seqs = [], 0, 0
    for m in TOKEN.finditer(f):
        lit = f[pos:m.start()]
        if lit:
            parts.append(("lit", lit))
        name = m.group(1)
        if name in ("le", "yyyy", "yy", "mm"):
            parts.append((name, None))
        else:
            sm = SEQ.fullmatch(name)
            if not sm or not 1 <= int(sm.group(1)) <= 18:
                raise NumError("FORMAT_INVALID")
            parts.append(("seq", int(sm.group(1))))
            seqs += 1
        pos = m.end()
    if f[pos:]:
        parts.append(("lit", f[pos:]))
    for kind, val in parts:
        if kind == "lit" and ("{" in val or "}" in val or any(ord(ch) < 0x20 or ord(ch) == 0x7F or ch.isspace() for ch in val)):
            raise NumError("FORMAT_INVALID")
    if seqs != 1:
        raise NumError("FORMAT_NO_SEQUENCE" if seqs == 0 else "FORMAT_INVALID")
    names = {k for k, _ in parts}
    if "mm" in names and not ({"yyyy", "yy"} & names):
        raise NumError("FORMAT_REPEATS")  # resets monthly but carries no year: repeats next year
    gran = "month" if "mm" in names else "year" if {"yyyy", "yy"} & names else "none"
    return parts, gran


def period_key(f, d):
    _, gran = compile_format(f)
    if gran == "month":
        return f"{d.year:04d}-{d.month:02d}"
    if gran == "year":
        return f"{d.year:04d}"
    return ""


def render(f, le, d, seq):
    parts, _ = compile_format(f)
    if not isinstance(seq, int) or seq < 1:
        raise NumError("SEQ_INVALID")
    if not isinstance(le, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", le):
        raise NumError("LEGAL_ENTITY_CODE_INVALID")
    out = []
    for kind, val in parts:
        if kind == "lit":
            out.append(val)
        elif kind == "le":
            out.append(le)
        elif kind == "yyyy":
            out.append(f"{d.year:04d}")
        elif kind == "yy":
            out.append(f"{d.year % 100:02d}")
        elif kind == "mm":
            out.append(f"{d.month:02d}")
        else:
            out.append(str(seq).zfill(val))  # wider than N: never truncated
    return "".join(out)


def simulate(inp):
    """Allocation model. gapless: transactions run one after another (the row
    lock serialises them); a rollback returns its numbers. gapped: each
    process reserves blocks of `block_size` in its own committed transaction
    and hands numbers out from memory; a rollback loses them."""
    mode = inp["mode"]
    nxt = {}  # (scope, period) -> next_value in the series row
    mem = {}  # gapped: (process, scope, period) -> [next, end)
    pending = {}  # tx -> list of (scope, period, n)
    committed = []
    for st in inp["steps"]:
        tx = st["tx"]
        if st["op"] == "alloc":
            key = (st["scope"], st["period"])
            if mode == "gapless":
                n = nxt.get(key, 1)
                nxt[key] = n + 1
            else:
                pk = (st["process"],) + key
                cur = mem.get(pk)
                if cur is None or cur[0] >= cur[1]:
                    start = nxt.get(key, 1)
                    nxt[key] = start + inp["block_size"]
                    cur = [start, start + inp["block_size"]]
                    mem[pk] = cur
                n = cur[0]
                cur[0] += 1
            pending.setdefault(tx, []).append((st["scope"], st["period"], n))
        elif st["op"] == "commit":
            for s, p, n in pending.pop(tx, []):
                committed.append({"tx": tx, "scope": s, "period": p, "number": n})
        elif st["op"] == "rollback":
            got = pending.pop(tx, [])
            if mode == "gapless":
                for s, p, n in got:
                    nxt[(s, p)] -= 1  # the row update is undone
        elif st["op"] == "crash":
            mem = {k: v for k, v in mem.items() if k[0] != st["process"]}
    rows = [{"scope": s, "period": p, "next_value": v} for (s, p), v in sorted(nxt.items())]
    return {"committed": committed, "series_rows": rows}


D = dt.date


def gen_format():
    c = CaseList("numbering", "format")

    def add(slug, why, f, le="LE01", d="2026-10-02", seq=12):
        inp = {"format": f, "legal_entity_code": le, "business_date": d, "seq": seq}
        try:
            c.add(slug, why, "format_number", inp, expected={"number": render(f, le, D.fromisoformat(d), seq)}, refs=["P11.10"])
        except NumError as e:
            c.add(slug, why, "format_number", inp, error=e.reason, refs=["P11.10"])

    add("sales-order-default", "the documented default SO{yyyy}{mm}-{seq:05}", "SO{yyyy}{mm}-{seq:05}")
    add("with-legal-entity", "legal entity code in the number", "{le}-SO{yyyy}{mm}-{seq:05}")
    add("two-digit-year", "{yy}", "INV{yy}{mm}{seq:04}")
    add("yearly", "a yearly series", "PO{yyyy}-{seq:06}")
    add("never-resets", "no date part: one series forever", "C{seq:08}")
    add("voucher-cjk", "a Chinese voucher prefix", "记-{yyyy}{mm}-{seq:04}")
    add("seq-wider-than-width", "a sequence beyond the width widens, never truncates", "SO{yyyy}{mm}-{seq:05}", seq=123456)
    add("seq-width-1", "width 1", "X{seq:1}", seq=7)
    add("seq-width-18", "width 18", "X{seq:18}", seq=1)
    add("january", "month is zero-padded", "SO{yyyy}{mm}-{seq:05}", d="2027-01-31", seq=1)
    add("year-2000-yy", "{yy} of 2000 is 00", "Y{yy}-{seq:03}", d="2000-06-01", seq=5)
    add("unknown-placeholder", "{dd} is not a placeholder", "SO{yyyy}{mm}{dd}-{seq:05}")
    add("seq-no-width", "{seq} needs a width", "SO{seq}")
    add("seq-width-zero", "width 0", "SO{seq:0}")
    add("seq-width-19", "width above 18", "SO{seq:19}")
    add("seq-width-unpadded", "{seq:5} and {seq:05} mean the same width", "SO{seq:5}")
    add("seq-width-three-digits", "a width has at most two digits", "SO{seq:005}")
    add("seq-width-zero-padded-zero", "{seq:00} is width 0", "SO{seq:00}")
    add("two-seq", "two sequences", "{seq:03}-{seq:03}")
    add("no-seq", "no sequence: numbers would repeat", "SO{yyyy}{mm}")
    add("month-without-year", "monthly reset without a year repeats every year", "SO{mm}-{seq:05}")
    add("unbalanced-open", "an unclosed brace", "SO{yyyy-{seq:05}")
    add("unbalanced-close", "a stray closing brace", "SO}{seq:05}")
    add("whitespace", "whitespace in a literal", "SO {seq:05}")
    add("upper-case-placeholder", "placeholders are lower case", "SO{YYYY}-{seq:05}")
    add("empty", "an empty format", "")
    add("seq-zero", "sequences start at 1", "SO{seq:05}", seq=0)
    add("bad-legal-entity-code", "a legal entity code with a space", "{le}{seq:03}", le="LE 01")
    return c


def gen_period():
    c = CaseList("numbering", "period")
    for slug, f, d, why in [
        ("monthly", "SO{yyyy}{mm}-{seq:05}", "2026-10-02", "a format with {mm} resets monthly"),
        ("monthly-yy", "INV{yy}{mm}{seq:04}", "2026-12-31", "{yy}{mm} resets monthly too"),
        ("yearly", "PO{yyyy}-{seq:06}", "2026-10-02", "a format with only a year resets yearly"),
        ("yearly-yy", "Y{yy}-{seq:03}", "2026-01-01", "{yy} alone resets yearly"),
        ("never", "C{seq:08}", "2026-10-02", "no date part: the period key is empty"),
        ("le-only", "{le}-{seq:06}", "2026-10-02", "the legal entity is the scope, not the period"),
        ("month-without-year", "SO{mm}-{seq:05}", "2026-10-02", "rejected"),
    ]:
        inp = {"format": f, "business_date": d}
        try:
            c.add(slug, why, "period_key", inp, expected={"period": period_key(f, D.fromisoformat(d))}, refs=["P11.10"])
        except NumError as e:
            c.add(slug, why, "period_key", inp, error=e.reason, refs=["P11.10"])
    return c


def gen_series():
    c = CaseList("numbering", "series")
    A = lambda tx, s="LE01", p="2026-10", **kw: dict({"tx": tx, "op": "alloc", "scope": s, "period": p}, **kw)  # noqa: E731
    C = lambda tx: {"tx": tx, "op": "commit"}  # noqa: E731
    R = lambda tx: {"tx": tx, "op": "rollback"}  # noqa: E731
    for slug, mode, steps, extra, why in [
        ("gapless-sequential", "gapless", [A("t1"), C("t1"), A("t2"), C("t2"), A("t3"), C("t3")], {},
         "consecutive commits get 1, 2, 3"),
        ("gapless-rollback-returns", "gapless", [A("t1"), C("t1"), A("t2"), R("t2"), A("t3"), C("t3")], {},
         "a rolled-back number is handed out again: no gap"),
        ("gapless-per-period", "gapless", [A("t1", p="2026-10"), C("t1"), A("t2", p="2026-11"), C("t2"),
                                            A("t3", p="2026-10"), C("t3")], {},
         "each period counts from 1"),
        ("gapless-per-legal-entity", "gapless", [A("t1", s="LE01"), C("t1"), A("t2", s="LE02"), C("t2"),
                                                  A("t3", s="LE01"), C("t3")], {},
         "each legal entity counts separately"),
        ("gapless-two-in-one-tx", "gapless", [A("t1"), A("t1"), C("t1"), A("t2"), C("t2")], {},
         "two vouchers in one transaction"),
        ("gapless-fiscal-period-key", "gapless", [A("t1", p="2026-P07"), C("t1"), A("t2", p="2026-P07"), C("t2")], {},
         "a voucher series keyed by fiscal period"),
        ("gapped-block", "gapped", [A("t1", process="p1"), C("t1"), A("t2", process="p1"), C("t2")],
         {"block_size": 10}, "numbers come from the process's block"),
        ("gapped-rollback-gap", "gapped", [A("t1", process="p1"), R("t1"), A("t2", process="p1"), C("t2")],
         {"block_size": 10}, "a rollback leaves a gap: 1 is lost, 2 is used"),
        ("gapped-two-processes", "gapped", [A("t1", process="p1"), C("t1"), A("t2", process="p2"), C("t2"),
                                            A("t3", process="p1"), C("t3")], {"block_size": 10},
         "two replicas: unique, increasing within a process, not across"),
        ("gapped-block-exhausted", "gapped", [A("t1", process="p1"), A("t1", process="p1"), A("t1", process="p1"),
                                              C("t1")], {"block_size": 2}, "the third number reserves a new block"),
        ("gapped-crash", "gapped", [A("t1", process="p1"), C("t1"), {"tx": "-", "op": "crash", "process": "p1"},
                                    A("t2", process="p1"), C("t2")], {"block_size": 10},
         "after a crash the rest of the block is lost"),
    ]:
        inp = dict({"mode": mode, "steps": steps}, **extra)
        c.add(slug, why, "series_sim", inp, expected=simulate(inp), refs=["P11.10"])
    return c


def main():
    counts = {}
    for topic, fn in [("format", gen_format), ("period", gen_period), ("series", gen_series)]:
        counts[topic] = write_file(os.path.join(OUT, f"{topic}.json"), "numbering", topic, GEN, fn())
    print("numbering", counts, "total", sum(counts.values()))


if __name__ == "__main__":
    main()
