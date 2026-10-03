#!/usr/bin/env python3
"""Generate vectors/envelope/*.json (protocol P11.5, P12; foundations 04, 12, 13).

Covers: UUIDv7 ids and IDTime; the CloudEvents headers derived from an
outbox row; causation and hop count derived from the publishing context;
what a consumer does with an inbound message (handle or dead-letter); the
state-mode cursor; redelivery and dead letters; stream, durable and
dead-letter names. xcheck_envelope.mjs recomputes every case in Node.
"""

import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_lib"))
from vecfile import CaseList, area_dir, write_file  # noqa: E402

GEN = "envelope/gen/gen_envelope.py"
OUT = area_dir(__file__)

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
SEG = r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*"  # P12.3: lowercase, starts with a letter, single inner underscores
SUBJECT_RE = re.compile(SEG + r"(?:\." + SEG + r"){2,}\.v[1-9][0-9]*")
COMPONENT_RE = re.compile(r"[a-z][a-z0-9]*/[a-z][a-z0-9-]*")
MAX_HOP = 10


class EnvError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def make_uuid7(ms, rand_a=0x7CC, rand_b=0x1A523F1D2E4B5A60):
    """Build a UUIDv7 from a millisecond timestamp and fixed random bits."""
    n = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    h = f"{n:032x}"
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def ms_of(iso):
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (t - dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)) // dt.timedelta(milliseconds=1)


def fmt_instant(t):
    """RFC 3339 UTC, 'Z', fractional seconds only when non-zero, trailing zeros removed (max 6 digits)."""
    t = t.astimezone(dt.timezone.utc)
    s = t.strftime("%Y-%m-%dT%H:%M:%S")
    if t.microsecond:
        s += "." + f"{t.microsecond:06d}".rstrip("0")
    return s + "Z"


def parse_instant(s):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})", s):
        raise EnvError("ENVELOPE_INVALID")
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def uuid7(s):
    if not isinstance(s, str) or not UUID_RE.fullmatch(s):
        raise EnvError("ID_INVALID")
    h = s.replace("-", "").lower()
    if h[12] != "7":
        raise EnvError("ID_INVALID")
    if h[16] not in "89ab":
        raise EnvError("ID_INVALID")
    ms = int(h[:12], 16)
    t = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(milliseconds=ms)
    return {"canonical": s.lower(), "unix_ms": ms, "created_at": fmt_instant(t)}


def subject_ok(s):
    return isinstance(s, str) and bool(SUBJECT_RE.fullmatch(s))


def stream_of(subject):
    if not subject_ok(subject):
        raise EnvError("SUBJECT_INVALID")
    first = subject.split(".")[0]
    return {"stream": "BE_" + first.upper(), "filter": first + ".>"}


def durable_of(component, subject):
    if not COMPONENT_RE.fullmatch(component):
        raise EnvError("COMPONENT_INVALID")
    if not subject_ok(subject):
        raise EnvError("SUBJECT_INVALID")
    # P12.5: '.' -> '__' is injective because no segment contains '__' or starts or ends with '_'
    return component.replace("/", "_") + "__" + subject.replace(".", "__")


MAX_PAYLOAD = 65536  # bytes of the serialised payload (P12.2)


def sized_payload(n):
    # a JSON object of exactly n bytes
    head, tail = '{"widget_id":"x","note":"', '"}'
    return head + "a" * (n - len(head) - len(tail)) + tail


def envelope(inp):
    p, row = inp["producer"], inp["row"]
    if not subject_ok(row["subject"]):
        raise EnvError("SUBJECT_INVALID")
    rid = uuid7(row["id"])["canonical"]
    if not isinstance(row["aggregate_version"], int) or row["aggregate_version"] < 1:
        raise EnvError("ENVELOPE_INVALID")
    if not row["aggregate_id"]:
        raise EnvError("ENVELOPE_INVALID")
    if len(row["payload_json"].encode("utf-8")) > MAX_PAYLOAD:
        raise EnvError("PAYLOAD_TOO_LARGE")  # P12.2: above 64 KiB a claim check, never a bigger event
    payload = json.loads(row["payload_json"])
    le = payload.get("legal_entity_id") if isinstance(payload, dict) else None
    if inp.get("contract", {}).get("transaction_document") and not (isinstance(le, str) and le):
        raise EnvError("LEGAL_ENTITY_MISSING")
    h = {
        "ce-specversion": "1.0",
        "ce-id": rid,
        "ce-source": p["component_id"],
        "ce-type": row["subject"],
        "ce-time": fmt_instant(parse_instant(row["occurred_at"])),
        "ce-subject": row["aggregate_id"],
        "content-type": "application/json",
        "ce-dataschema": f'{p["component_id"]}@{p["version"]}/contracts/events/{p["events_file"]}#{row["subject"]}',
        "ce-aggregatetype": row["aggregate_type"],
        "ce-aggregateversion": str(row["aggregate_version"]),
        "ce-hopcount": str(row["hop_count"]),
        "Nats-Msg-Id": rid,
    }
    if row["causation_id"]:
        h["ce-causationid"] = row["causation_id"]
    if isinstance(le, str) and le:
        h["ce-legalentity"] = le
    if row["traceparent"]:
        h["traceparent"] = row["traceparent"]
    if row.get("tracestate"):
        h["tracestate"] = row["tracestate"]
    return {"headers": dict(sorted(h.items()))}


def derive(ctx):
    k = ctx["kind"]
    if k == "request":
        return {"causation_id": "", "hop_count": 0}
    if k == "event":
        return {"causation_id": ctx["handled"]["id"], "hop_count": ctx["handled"]["hop_count"] + 1}
    if k == "queued_job":
        return {"causation_id": ctx["job"]["causation_id"], "hop_count": ctx["job"]["hop_count"]}
    if k in ("cron", "singleton", "every", "reconciler"):
        return {"causation_id": "", "hop_count": 0}
    raise KeyError(k)


def accept(inp):
    """Consumer side: handle the message, or dead-letter it with a reason."""
    h = inp["headers"]
    sub = inp["subscription"]
    durable = durable_of(sub["component_id"], sub["subject"])

    def dlq(reason):
        return {"action": "dlq", "dlq_subject": f"dlq.{durable}.{sub['subject']}",
                "added_headers": {"be-dlq-consumer": durable, "be-dlq-delivery": str(inp["delivery"]),
                                  "be-dlq-reason": reason}}

    try:
        if h.get("ce-specversion") != "1.0":
            raise EnvError("ENVELOPE_INVALID")
        for k in ("ce-id", "ce-source", "ce-type", "ce-time", "ce-subject", "ce-aggregatetype",
                  "ce-aggregateversion", "ce-hopcount"):
            if not h.get(k):
                raise EnvError("ENVELOPE_INVALID")
        uuid7(h["ce-id"])
        if h["ce-type"] != sub["subject"]:
            raise EnvError("ENVELOPE_INVALID")
        if h.get("content-type") != "application/json":
            raise EnvError("ENVELOPE_INVALID")
        if h["ce-aggregatetype"] != sub["aggregate_type"]:
            raise EnvError("ENVELOPE_INVALID")
        for k in ("ce-aggregateversion", "ce-hopcount"):
            if not re.fullmatch(r"0|[1-9][0-9]{0,17}", h[k]):
                raise EnvError("ENVELOPE_INVALID")
        if int(h["ce-aggregateversion"]) < 1:
            raise EnvError("ENVELOPE_INVALID")
        parse_instant(h["ce-time"])
        hop = int(h["ce-hopcount"])
        if hop > MAX_HOP:
            raise EnvError("HOP_LIMIT")
        try:
            payload = json.loads(inp["payload_json"])
        except ValueError:
            raise EnvError("PAYLOAD_INVALID")
        if not isinstance(payload, dict):
            raise EnvError("PAYLOAD_INVALID")
        if sub.get("transaction_document"):
            if not h.get("ce-legalentity") or payload.get("legal_entity_id") != h["ce-legalentity"]:
                raise EnvError("LEGAL_ENTITY_MISSING")
    except EnvError as e:
        if e.reason == "ID_INVALID":
            return dlq("ENVELOPE_INVALID")
        return dlq(e.reason)
    return {"action": "handle", "event": {
        "id": h["ce-id"].lower(), "subject": h["ce-type"], "source": h["ce-source"],
        "aggregate_type": h["ce-aggregatetype"], "aggregate_id": h["ce-subject"],
        "version": int(h["ce-aggregateversion"]), "hop_count": hop,
        "causation_id": h.get("ce-causationid", ""), "occurred_at": fmt_instant(parse_instant(h["ce-time"])),
        "legal_entity": h.get("ce-legalentity", ""), "delivery": inp["delivery"]}}


def cursor_run(versions, start):
    cur = start
    applied = []
    for v in versions:
        if cur is None or v > cur:
            applied.append(v)
            cur = v
    return {"applied": applied, "final": cur}


def redelivery(inp):
    # P12.7: the runtime counts deliveries (the broker's max_deliver is -1, no server backoff).
    # On receipt a delivery above max_deliver is dead-lettered without running the handler.
    d, mx, bo, out = inp["delivery"], inp["max_deliver"], inp["backoff"], inp["outcome"]
    msg_id = f"dlq:{inp['durable']}:{inp['stream_seq']}"
    if d > mx:
        return {"action": "dlq", "reason": "MAX_DELIVER", "handled": False, "dlq_msg_id": msg_id}
    if out == "ok":
        return {"action": "ack", "handled": True}
    if out == "permanent":
        return {"action": "dlq", "reason": "PERMANENT", "handled": True, "dlq_msg_id": msg_id}
    return {"action": "nak", "delay": bo[min(d - 1, len(bo) - 1)], "handled": True}



# ---------------------------------------------------------------- cases

T0 = "2026-10-02T08:00:00.123Z"
ID0 = make_uuid7(ms_of(T0))
ID1 = make_uuid7(ms_of("2026-10-02T08:00:01.456Z"), rand_a=0x123, rand_b=0x2000000000000001)
ID2 = make_uuid7(ms_of("2026-10-02T08:00:02Z"), rand_a=0xABC, rand_b=0x3FFFFFFFFFFFFFFF)
TP = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def gen_ids():
    c = CaseList("envelope", "ids")

    def add(slug, why, s):
        try:
            c.add(slug, why, "uuid7", {"id": s}, expected=uuid7(s), refs=["P11.5", "P12"])
        except EnvError as e:
            c.add(slug, why, "uuid7", {"id": s}, error=e.reason, refs=["P11.5", "P12"])

    add("valid", "a UUIDv7; IDTime gives created_at to the millisecond", ID0)
    add("valid-2", "another UUIDv7", ID1)
    add("valid-whole-second", "created_at without a fraction", ID2)
    add("epoch", "the smallest v7 timestamp", make_uuid7(0, 0, 0))
    add("far-future", "a timestamp in 2199", make_uuid7(ms_of("2199-12-31T23:59:59.999Z"), 0xFFF, 2 ** 62 - 1))
    add("upper-case", "upper-case hex is accepted on input and normalised (RFC 9562)", ID0.upper())
    add("version-4", "a UUIDv4 is not a v7", "0192f0c4-7b1e-4cc3-9a52-3f1d2e4b5a60")
    add("version-1", "a UUIDv1 is not a v7", "0192f0c4-7b1e-1cc3-9a52-3f1d2e4b5a60")
    add("variant-ncs", "variant bits 0xxx", "0192f0c4-7b1e-7cc3-1a52-3f1d2e4b5a60")
    add("variant-microsoft", "variant bits 110x", "0192f0c4-7b1e-7cc3-ca52-3f1d2e4b5a60")
    add("nil", "the nil UUID", "00000000-0000-0000-0000-000000000000")
    add("max", "the max UUID", "ffffffff-ffff-ffff-ffff-ffffffffffff")
    add("braces", "braces are not the canonical form", "{" + ID0 + "}")
    add("urn", "the urn:uuid: form is not accepted", "urn:uuid:" + ID0)
    add("no-hyphens", "32 hex digits without hyphens", ID0.replace("-", ""))
    add("whitespace", "surrounding whitespace", " " + ID0)
    add("trailing-newline", "a trailing newline", ID0 + "\n")
    add("short", "35 characters", ID0[:-1])
    add("non-hex", "a non-hex digit", ID0[:-1] + "g")
    add("empty", "empty", "")
    return c


def row(**kw):
    r = {"id": ID0, "subject": "conformance.widget.created.v1", "aggregate_type": "conformance.widget.widget",
         "aggregate_id": "0192f0c4-0000-7000-8000-00000000aaaa", "aggregate_version": 1,
         "occurred_at": "2026-10-02T08:00:00.123456Z", "traceparent": TP, "causation_id": "", "hop_count": 0,
         "payload_json": '{"widget_id":"0192f0c4-0000-7000-8000-00000000aaaa","legal_entity_id":"LE01"}'}
    r.update(kw)
    return r


PRODUCER = {"component_id": "conformance/widget", "version": "1.0.0", "events_file": "widget.events.json"}


def gen_headers():
    c = CaseList("envelope", "headers")

    def add(slug, why, inp):
        try:
            c.add(slug, why, "envelope", inp, expected=envelope(inp), refs=["P12"])
        except EnvError as e:
            c.add(slug, why, "envelope", inp, error=e.reason, refs=["P12"])

    add("from-request", "published from a user request: hop 0, no causation header", {"producer": PRODUCER, "row": row()})
    add("from-handler", "published in an event handler", {"producer": PRODUCER, "row": row(
        id=ID1, aggregate_version=7, causation_id=ID2, hop_count=3, occurred_at="2026-10-02T08:00:01.456Z")})
    add("offset-time", "occurred_at with an offset becomes UTC Z", {"producer": PRODUCER, "row": row(
        occurred_at="2026-10-02T07:30:00+08:00")})
    add("whole-second", "no fraction when the time is a whole second", {"producer": PRODUCER, "row": row(
        occurred_at="2026-10-02T08:00:00.000000Z")})
    add("trailing-zeros", "fractional trailing zeros are removed", {"producer": PRODUCER, "row": row(
        occurred_at="2026-10-02T08:00:00.120000Z")})
    add("no-traceparent", "no traceparent header when the row has none", {"producer": PRODUCER, "row": row(traceparent="")})
    add("no-legal-entity", "a master-data event without legal_entity_id has no ce-legalentity",
        {"producer": {"component_id": "conformance/peer", "version": "1.0.0", "events_file": "peer.events.json"},
         "row": row(subject="conformance.owner.updated.v1", aggregate_type="conformance.peer.owner",
                    aggregate_id="owner-7", payload_json='{"owner_id":"owner-7","display_name":"A"}')})
    add("legal-entity-required-missing", "a transaction-document event must carry legal_entity_id",
        {"producer": PRODUCER, "contract": {"transaction_document": True},
         "row": row(payload_json='{"widget_id":"x"}')})
    add("legal-entity-required-empty", "an empty legal_entity_id counts as missing",
        {"producer": PRODUCER, "contract": {"transaction_document": True},
         "row": row(payload_json='{"widget_id":"x","legal_entity_id":""}')})
    add("legacy-subject", "a legacy first segment keeps its own stream", {"producer": {
        "component_id": "erp/sales", "version": "3.0.0", "events_file": "sales.events.json"},
        "row": row(subject="sales.order.created.v1", aggregate_type="erp.sales.order")})
    add("shell-member", "in a shell ce-source is the member's ID", {"producer": dict(PRODUCER, component_id="conformance/widget-go"),
                                                                    "row": row()})
    add("tracestate", "the outbox row's tracestate travels next to traceparent", {"producer": PRODUCER, "row": row(
        tracestate="vendor1=opaque1,vendor2=opaque2")})
    add("payload-at-limit", "a payload of exactly 64 KiB is published", {"producer": PRODUCER, "row": row(
        payload_json=sized_payload(MAX_PAYLOAD))})
    add("payload-above-limit", "a payload above 64 KiB is refused at publish: use a claim check", {"producer": PRODUCER, "row": row(
        payload_json=sized_payload(MAX_PAYLOAD + 1))})
    add("bad-subject", "a subject that breaks the naming rule", {"producer": PRODUCER, "row": row(subject="Widget.Created")})
    add("bad-id", "the outbox id must be a UUIDv7", {"producer": PRODUCER, "row": row(id="0192f0c4-7b1e-4cc3-9a52-3f1d2e4b5a60")})
    add("version-zero", "aggregate versions start at 1", {"producer": PRODUCER, "row": row(aggregate_version=0)})
    return c


def gen_derive():
    c = CaseList("envelope", "derive")
    for slug, ctx, why in [
        ("request", {"kind": "request"}, "a user request or a system rpc starts a chain"),
        ("event", {"kind": "event", "handled": {"id": ID1, "hop_count": 0}}, "first hop"),
        ("event-deep", {"kind": "event", "handled": {"id": ID1, "hop_count": 9}}, "hop 9 publishes hop 10"),
        ("event-at-limit", {"kind": "event", "handled": {"id": ID1, "hop_count": 10}},
         "hop 10 publishes hop 11; publishing is never refused, the consumer dead-letters it"),
        ("queued-job", {"kind": "queued_job", "job": {"causation_id": ID1, "hop_count": 2}},
         "a queued job publishes with the values captured when it was enqueued"),
        ("queued-job-from-request", {"kind": "queued_job", "job": {"causation_id": "", "hop_count": 0}},
         "a job enqueued in a request"),
        ("cron", {"kind": "cron"}, "a cron run starts a chain"),
        ("singleton", {"kind": "singleton"}, "a singleton run starts a chain"),
        ("reconciler", {"kind": "reconciler"}, "a reconciler step starts a chain"),
    ]:
        c.add(slug, why, "derive", {"context": ctx}, expected=derive(ctx), refs=["P12.8"])
    for slug, ctx, why in [
        ("enqueue-in-request", {"kind": "request"}, "the job row stores what an event published now would carry"),
        ("enqueue-in-handler", {"kind": "event", "handled": {"id": ID1, "hop_count": 4}}, "inherits the handled event"),
        ("enqueue-in-cron", {"kind": "cron"}, "a cron run starts a chain"),
    ]:
        d = derive(ctx)
        c.add(slug, why, "enqueue_context", {"context": ctx},
              expected={"job_causation_id": d["causation_id"], "job_hop_count": d["hop_count"]}, refs=["P12.8", "P14"])
    return c


def good_headers(**kw):
    h = envelope({"producer": PRODUCER, "row": row()})["headers"]
    h = {k: v for k, v in h.items() if k != "Nats-Msg-Id"}
    for k, v in kw.items():
        k = k.replace("_", "-")
        if v is None:
            h.pop(k, None)
        else:
            h[k] = v
    return h


SUB = {"component_id": "conformance/peer", "subject": "conformance.widget.created.v1",
       "aggregate_type": "conformance.widget.widget", "transaction_document": True}
PAY = '{"widget_id":"0192f0c4-0000-7000-8000-00000000aaaa","legal_entity_id":"LE01"}'


def gen_inbound():
    c = CaseList("envelope", "inbound")

    def add(slug, why, headers, payload=PAY, sub=SUB, delivery=1):
        inp = {"subscription": sub, "headers": headers, "payload_json": payload, "delivery": delivery}
        c.add(slug, why, "accept", inp, expected=accept(inp), refs=["P12", "P11.8"])

    add("valid", "a complete envelope is handled", good_headers())
    add("valid-with-causation", "causation and hop count are read", good_headers(ce_causationid=ID2, ce_hopcount="4"))
    add("hop-10", "hop count 10 is still handled", good_headers(ce_hopcount="10"))
    add("hop-11", "hop count above 10 goes to the dead letters", good_headers(ce_hopcount="11"))
    add("missing-id", "no ce-id", good_headers(ce_id=None))
    add("id-not-v7", "ce-id is a UUIDv4", good_headers(ce_id="0192f0c4-7b1e-4cc3-9a52-3f1d2e4b5a60"))
    add("legacy-x-headers", "only the old X- headers: never read", {
        "X-Aggregate-Id": "a", "X-Version": "1", "X-Trace-Id": "t", "X-Causation-Id": "", "X-Hop-Count": "0"})
    add("specversion-0-3", "CloudEvents 0.3", good_headers(ce_specversion="0.3"))
    add("missing-hopcount", "ce-hopcount is always set by producers", good_headers(ce_hopcount=None))
    add("hopcount-negative", "a negative hop count", good_headers(ce_hopcount="-1"))
    add("hopcount-text", "a non-numeric hop count", good_headers(ce_hopcount="three"))
    add("hopcount-leading-zero", "a hop count with a leading zero", good_headers(ce_hopcount="03"))
    add("version-zero", "aggregate version 0", good_headers(ce_aggregateversion="0"))
    add("version-text", "aggregate version not an integer", good_headers(ce_aggregateversion="v2"))
    add("aggregate-type-mismatch", "the header's aggregate type differs from the contract", good_headers(
        ce_aggregatetype="conformance.widget.other"))
    add("type-mismatch", "ce-type is not the subscribed subject", good_headers(ce_type="conformance.widget.approved.v1"))
    add("content-type", "a non-JSON content type", good_headers(content_type="application/protobuf"))
    add("bad-time", "ce-time is not RFC 3339", good_headers(ce_time="2026-10-02 08:00:00"))
    add("payload-not-json", "the payload does not parse", good_headers(), payload="{not json")
    add("payload-array", "the payload is not an object", good_headers(), payload="[1,2]")
    add("legal-entity-missing", "a transaction-document event without ce-legalentity", good_headers(ce_legalentity=None))
    add("legal-entity-disagrees", "header and payload legal entities differ", good_headers(ce_legalentity="LE02"))
    add("legal-entity-not-required", "master data needs no legal entity", good_headers(ce_legalentity=None),
        payload='{"widget_id":"x"}', sub=dict(SUB, transaction_document=False))
    add("redelivered", "the delivery count is carried to the handler and to dead letters", good_headers(ce_hopcount="11"),
        delivery=3)
    add("shell-member-consumer", "durable and dead-letter subject use the member's ID", good_headers(ce_hopcount="12"),
        sub=dict(SUB, component_id="conformance/widget-go"))
    return c


def gen_cursor():
    c = CaseList("envelope", "cursor")
    for slug, start, vs, why in [
        ("in-order", None, [1, 2, 3], "in order, every version applied"),
        ("duplicate", None, [1, 1, 2, 2], "duplicates are skipped"),
        ("out-of-order", None, [3, 2, 1], "v3 first: v2 and v1 are older and skipped"),
        ("gap", None, [1, 4], "gaps are fine in state mode"),
        ("shuffled-with-duplicates", None, [2, 5, 1, 5, 3, 4, 5, 2], "the final state equals one in-order delivery"),
        ("existing-cursor", 4, [3, 4, 5], "the cursor already at 4"),
        ("equal-is-skip", 7, [7], "an equal version is a duplicate"),
    ]:
        c.add(slug, why, "cursor_sequence", {"start": start, "versions": vs}, expected=cursor_run(vs, start), refs=["P12.6"])
    bo = ["1s", "10s", "1m", "5m", "15m", "30m", "1h"]
    for slug, d, mx, out, b, why in [
        ("ok", 1, 8, "ok", bo, "a successful handler acks"),
        ("first-failure", 1, 8, "error", bo, "first failure: wait the first backoff"),
        ("third-failure", 3, 8, "error", bo, "third failure: the third backoff"),
        ("seventh-failure", 7, 8, "error", bo, "seventh failure: the last backoff"),
        ("last-allowed-failure", 8, 8, "error", bo, "the last allowed delivery fails: nak; the next delivery is dead-lettered on receipt"),
        ("over-max-deliver", 9, 8, "error", bo, "a delivery above max_deliver is dead-lettered on receipt; the handler does not run"),
        ("permanent", 1, 8, "permanent", bo, "a permanent error goes straight to the dead letters"),
        ("short-list", 5, 8, "error", ["1s", "10s"], "a backoff list shorter than max_deliver repeats its last value"),
        ("conformance-tuning", 2, 3, "error", ["200ms", "500ms", "1s"], "the compconf tuning EVENTS_BACKOFF=200ms,500ms,1s"),
        ("conformance-last-allowed", 3, 3, "error", ["200ms", "500ms", "1s"], "EVENTS_MAX_DELIVER=3: the third failure still naks"),
        ("conformance-over", 4, 3, "error", ["200ms", "500ms", "1s"], "EVENTS_MAX_DELIVER=3: the fourth delivery goes to the dead letters"),
        ("permanent-msg-id", 2, 8, "permanent", bo, "the dead-letter message ID is dlq:<durable>:<stream sequence>, so a crash never duplicates it"),
    ]:
        inp = {"delivery": d, "max_deliver": mx, "backoff": b, "outcome": out,
               "durable": "conformance_widget-go__conformance__owner__updated__v1", "stream_seq": 40 + d}
        c.add(slug, why, "redelivery", inp, expected=redelivery(inp), refs=["P12.5", "P12.7"])
    return c


def gen_names():
    c = CaseList("envelope", "names")
    for s in ["sales.order.created.v1", "erp.inventory.adjusted.v1", "infra.authz.changed.v1",
              "integration.im.result.v1", "conformance.widget.created.v1", "crm.opportunity.stage_changed.v1",
              "finance.credit.rejected.v1", "infra.notification.dispatch.im.v1"]:
        c.add("stream-" + s.replace(".", "-").replace("_", "-"), f"stream of {s}", "stream", {"subject": s},
              expected=stream_of(s), refs=["P12.4"])
    for slug, s, why in [
        ("subject-three-segments", "erp.created.v1", "fewer than four segments"),
        ("subject-upper-case", "ERP.inventory.adjusted.v1", "upper case"),
        ("subject-hyphen", "integration.im-dingtalk.sent.v1", "a hyphen in a segment"),
        ("subject-no-version", "erp.inventory.adjusted", "no version segment"),
        ("subject-version-zero", "erp.inventory.adjusted.v0", "versions start at v1"),
        ("subject-wildcard", "erp.inventory.*.v1", "a wildcard"),
        ("subject-empty-segment", "erp..adjusted.v1", "an empty segment"),
        ("subject-leading-underscore", "erp._inventory.adjusted.v1", "a segment starting with an underscore"),
        ("subject-trailing-underscore", "erp.inventory_.adjusted.v1", "a segment ending with an underscore"),
        ("subject-double-underscore", "erp.stock__level.changed.v1", "a double underscore"),
        ("subject-leading-digit", "erp.2fa.enabled.v1", "a segment starting with a digit"),
    ]:
        try:
            stream_of(s)
            raise AssertionError(s)
        except EnvError as e:
            c.add(slug, f"{s!r}: {why}", "stream", {"subject": s}, error=e.reason, refs=["P12.3"])
    for comp, s in [("erp/finance", "sales.order.created.v1"), ("integration/im-dingtalk", "infra.notification.dispatch.im.v1"),
                    ("crm/opportunity", "erp.sales.order.created.v1"), ("conformance/widget-go", "conformance.owner.updated.v1"),
                    ("mdm/customer", "crm.opportunity.stage_changed.v1")]:
        d = durable_of(comp, s)
        c.add("durable-" + comp.replace("/", "-") + "-" + s.split(".")[1], f"durable of {comp} on {s}", "durable",
              {"component_id": comp, "subject": s}, expected={"durable": d, "dlq_subject": f"dlq.{d}.{s}"},
              refs=["P12.5", "P12.7"])
    for slug, comp, s in [("durable-bad-component", "erp.finance", "sales.order.created.v1"),
                          ("durable-bad-subject", "erp/finance", "sales.order.created")]:
        try:
            durable_of(comp, s)
            raise AssertionError(slug)
        except EnvError as e:
            c.add(slug, "invalid input", "durable", {"component_id": comp, "subject": s}, error=e.reason, refs=["P12.5"])
    for slug, comp, subs in [("durables-injective", "crm/opportunity", ["crm.lead.stage_changed.v1", "crm.lead_stage.changed.v1"])]:
        for s in subs:
            d = durable_of(comp, s)
            c.add(slug + "-" + s.split(".")[2].replace("_", "-"), "'.' becomes '__', so subjects that differ only by where '.' and '_' sit keep distinct names",
                  "durable", {"component_id": comp, "subject": s}, expected={"durable": d, "dlq_subject": f"dlq.{d}.{s}"}, refs=["P12.5"])
    return c


def main():
    counts = {}
    for topic, fn in [("ids", gen_ids), ("headers", gen_headers), ("derive", gen_derive), ("inbound", gen_inbound),
                      ("cursor", gen_cursor), ("names", gen_names)]:
        counts[topic] = write_file(os.path.join(OUT, f"{topic}.json"), "envelope", topic, GEN, fn())
    print("envelope", counts, "total", sum(counts.values()))


if __name__ == "__main__":
    main()
