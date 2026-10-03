// xcheck_envelope recomputes vectors/envelope/*.json in Node, written from
// the protocol text (P12, foundations 12/13) without looking at the Python
// generator's code paths. Prints every disagreement; exit 1 if any.
//
//   docker run --rm -v "$PWD":/v:ro node:22-alpine node /v/envelope/gen/xcheck_envelope.mjs /v/envelope
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { isDeepStrictEqual } from "node:util";

const dir = process.argv[2];
let bad = 0, n = 0;
class E extends Error { constructor(r) { super(r); this.reason = r; } }

const RFC3339 = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|([+-])(\d{2}):(\d{2}))$/;
function instant(s) {
  const m = RFC3339.exec(s);
  if (!m) throw new E("ENVELOPE_INVALID");
  let ms = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
  if (m[8] !== "Z") ms -= (m[9] === "+" ? 1 : -1) * (+m[10] * 60 + +m[11]) * 60000;
  const micro = (m[7] || "").padEnd(6, "0");
  return { ms, micro };
}
function fmt({ ms, micro }) {
  const base = new Date(ms).toISOString().slice(0, 19);
  const f = micro.replace(/0+$/, "");
  return base + (f ? "." + f : "") + "Z";
}
function uuid7(s) {
  if (typeof s !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(s))
    throw new E("ID_INVALID");
  const ms = Number(BigInt("0x" + s.replace(/-/g, "").slice(0, 12)));
  return { canonical: s.toLowerCase(), unix_ms: ms, created_at: fmt({ ms, micro: String(ms % 1000).padStart(3, "0") + "000" }) };
}
// P12.3: >= 4 segments; each starts with a letter, words joined by single underscores; last v<n>
const segOk = (g) => /^[a-z]/.test(g) && g.split("_").every((w) => /^[a-z0-9]+$/.test(w));
const subjectOk = (s) => {
  if (typeof s !== "string") return false;
  const parts = s.split(".");
  return parts.length >= 4 && parts.slice(0, -1).every(segOk) && /^v[1-9][0-9]*$/.test(parts[parts.length - 1]);
};
function stream(s) {
  if (!subjectOk(s)) throw new E("SUBJECT_INVALID");
  const first = s.split(".")[0];
  return { stream: "BE_" + first.toUpperCase(), filter: first + ".>" };
}
function durable(c, s) {
  if (!/^[a-z][a-z0-9]*\/[a-z][a-z0-9-]*$/.test(c)) throw new E("COMPONENT_INVALID");
  if (!subjectOk(s)) throw new E("SUBJECT_INVALID");
  return c.split("/").join("_") + "__" + s.split(".").join("__");
}
function envelope({ producer: p, row: r, contract }) {
  if (!subjectOk(r.subject)) throw new E("SUBJECT_INVALID");
  const id = uuid7(r.id).canonical;
  if (!Number.isInteger(r.aggregate_version) || r.aggregate_version < 1 || !r.aggregate_id) throw new E("ENVELOPE_INVALID");
  if (Buffer.byteLength(r.payload_json, "utf8") > 65536) throw new E("PAYLOAD_TOO_LARGE");
  const pl = JSON.parse(r.payload_json);
  const le = pl && typeof pl === "object" && !Array.isArray(pl) ? pl.legal_entity_id : undefined;
  const hasLe = typeof le === "string" && le.length > 0;
  if (contract?.transaction_document && !hasLe) throw new E("LEGAL_ENTITY_MISSING");
  const h = {
    "ce-specversion": "1.0", "ce-id": id, "ce-source": p.component_id, "ce-type": r.subject,
    "ce-time": fmt(instant(r.occurred_at)), "ce-subject": r.aggregate_id, "content-type": "application/json",
    "ce-dataschema": `${p.component_id}@${p.version}/contracts/events/${p.events_file}#${r.subject}`,
    "ce-aggregatetype": r.aggregate_type, "ce-aggregateversion": String(r.aggregate_version),
    "ce-hopcount": String(r.hop_count), "Nats-Msg-Id": id,
  };
  if (r.causation_id) h["ce-causationid"] = r.causation_id;
  if (hasLe) h["ce-legalentity"] = le;
  if (r.traceparent) h["traceparent"] = r.traceparent;
  if (r.tracestate) h["tracestate"] = r.tracestate;
  return { headers: Object.fromEntries(Object.entries(h).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))) };
}
function derive(c) {
  if (c.kind === "event") return { causation_id: c.handled.id, hop_count: c.handled.hop_count + 1 };
  if (c.kind === "queued_job") return { causation_id: c.job.causation_id, hop_count: c.job.hop_count };
  return { causation_id: "", hop_count: 0 };
}
function accept({ subscription: s, headers: h, payload_json, delivery }) {
  const d = durable(s.component_id, s.subject);
  const dlq = (reason) => ({ action: "dlq", dlq_subject: `dlq.${d}.${s.subject}`,
    added_headers: { "be-dlq-consumer": d, "be-dlq-delivery": String(delivery), "be-dlq-reason": reason } });
  const intOk = (v) => /^(0|[1-9][0-9]{0,17})$/.test(v);
  if (h["ce-specversion"] !== "1.0") return dlq("ENVELOPE_INVALID");
  for (const k of ["ce-id", "ce-source", "ce-type", "ce-time", "ce-subject", "ce-aggregatetype", "ce-aggregateversion", "ce-hopcount"])
    if (!h[k]) return dlq("ENVELOPE_INVALID");
  try { uuid7(h["ce-id"]); } catch { return dlq("ENVELOPE_INVALID"); }
  if (h["ce-type"] !== s.subject || h["content-type"] !== "application/json" || h["ce-aggregatetype"] !== s.aggregate_type)
    return dlq("ENVELOPE_INVALID");
  if (!intOk(h["ce-aggregateversion"]) || !intOk(h["ce-hopcount"]) || Number(h["ce-aggregateversion"]) < 1) return dlq("ENVELOPE_INVALID");
  let t;
  try { t = instant(h["ce-time"]); } catch { return dlq("ENVELOPE_INVALID"); }
  const hop = Number(h["ce-hopcount"]);
  if (hop > 10) return dlq("HOP_LIMIT");
  let pl;
  try { pl = JSON.parse(payload_json); } catch { return dlq("PAYLOAD_INVALID"); }
  if (!pl || typeof pl !== "object" || Array.isArray(pl)) return dlq("PAYLOAD_INVALID");
  if (s.transaction_document && (!h["ce-legalentity"] || pl.legal_entity_id !== h["ce-legalentity"])) return dlq("LEGAL_ENTITY_MISSING");
  return { action: "handle", event: { id: h["ce-id"].toLowerCase(), subject: h["ce-type"], source: h["ce-source"],
    aggregate_type: h["ce-aggregatetype"], aggregate_id: h["ce-subject"], version: Number(h["ce-aggregateversion"]),
    hop_count: hop, causation_id: h["ce-causationid"] ?? "", occurred_at: fmt(t), legal_entity: h["ce-legalentity"] ?? "", delivery } };
}
function cursor({ start, versions }) {
  let cur = start; const applied = [];
  for (const v of versions) if (cur === null || v > cur) { applied.push(v); cur = v; }
  return { applied, final: cur };
}
function redelivery({ delivery, max_deliver, backoff, outcome, durable: dur, stream_seq }) {
  const dlq_msg_id = `dlq:${dur}:${stream_seq}`;
  if (delivery > max_deliver) return { action: "dlq", reason: "MAX_DELIVER", handled: false, dlq_msg_id };
  if (outcome === "ok") return { action: "ack", handled: true };
  if (outcome === "permanent") return { action: "dlq", reason: "PERMANENT", handled: true, dlq_msg_id };
  return { action: "nak", delay: backoff[Math.min(delivery, backoff.length) - 1], handled: true };
}
function run(op, i) {
  switch (op) {
    case "uuid7": return uuid7(i.id);
    case "envelope": return envelope(i);
    case "derive": return derive(i.context);
    case "enqueue_context": { const d = derive(i.context); return { job_causation_id: d.causation_id, job_hop_count: d.hop_count }; }
    case "accept": return accept(i);
    case "cursor_sequence": return cursor(i);
    case "redelivery": return redelivery(i);
    case "stream": return stream(i.subject);
    case "durable": { const d = durable(i.component_id, i.subject); return { durable: d, dlq_subject: `dlq.${d}.${i.subject}` }; }
  }
  throw new Error("op " + op);
}
for (const t of ["ids", "headers", "derive", "inbound", "cursor", "names"]) {
  for (const c of JSON.parse(readFileSync(join(dir, t + ".json"), "utf8")).cases) {
    n++;
    let got;
    try { got = run(c.op, c.input); } catch (e) { if (!(e instanceof E)) throw e; got = { reason: e.reason }; }
    const want = c.expected ?? c.expected_error;
    if (!isDeepStrictEqual(got, want)) { bad++; console.log(`DISAGREE ${c.id}: want ${JSON.stringify(want)}\n   node got ${JSON.stringify(got)}`); }
  }
}
console.log(`envelope xcheck: ${n} cases, ${bad} disagreements`);
process.exit(bad ? 1 : 0);
