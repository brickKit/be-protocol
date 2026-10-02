// xcheck_idempotency recomputes vectors/idempotency/*.json with Node:
// JSON.parse, the npm package `canonicalize` (RFC 8785 reference by its
// authors) and node:crypto. No code is shared with gen_idempotency.py.
//
//   docker run --rm -v "$PWD":/v -w /v/idempotency/gen node:22-alpine \
//     sh -c 'npm i --silent --no-save canonicalize@2 >/dev/null && node xcheck_idempotency.mjs ..'
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { join } from "node:path";
import { isDeepStrictEqual } from "node:util";
import canonicalizeMod from "canonicalize";

const canonicalize = canonicalizeMod.default ?? canonicalizeMod;
const dir = process.argv[2];
let bad = 0, n = 0;

// I-JSON duplicate names: a small scanner over the (already valid) text.
function hasDuplicateNames(text) {
  let i = 0;
  const ws = () => { while (" \t\r\n".includes(text[i])) i++; };
  const str = () => { const s = i; i++; while (text[i] !== '"') { if (text[i] === "\\") i++; i++; } i++; return JSON.parse(text.slice(s, i)); };
  const val = () => {
    ws();
    if (text[i] === "{") {
      i++; const seen = new Set(); ws();
      if (text[i] === "}") { i++; return false; }
      for (;;) {
        ws(); const k = str(); if (seen.has(k)) return true; seen.add(k);
        ws(); i++; if (val()) return true; ws();
        if (text[i] === ",") { i++; continue; }
        i++; return false;
      }
    }
    if (text[i] === "[") {
      i++; ws(); if (text[i] === "]") { i++; return false; }
      for (;;) { if (val()) return true; ws(); if (text[i] === ",") { i++; continue; } i++; return false; }
    }
    if (text[i] === '"') { str(); return false; }
    while (i < text.length && !",]} \t\r\n".includes(text[i])) i++;
    return false;
  };
  return val();
}

function finite(v) {
  if (typeof v === "number") return Number.isFinite(v);
  if (Array.isArray(v)) return v.every(finite);
  if (v && typeof v === "object") return Object.values(v).every(finite);
  return true;
}

function fingerprint(text) {
  let v;
  try { v = JSON.parse(text); } catch { return { error: "JSON_INVALID" }; }
  // canonicalize() would print a non-finite number as null: reject it first.
  if (!finite(v) || hasDuplicateNames(text)) return { error: "JSON_INVALID" };
  const canonical = canonicalize(v);
  return { canonical, sha256: createHash("sha256").update(canonical, "utf8").digest("hex") };
}

function ns(c) {
  return c.kind === "user" ? "user:" + c.sub : c.kind === "system_call" ? "svc:" + c.be_caller : "system";
}

function decide(inp) {
  const inc = inp.incoming, caller = ns(inc.caller), now = Date.parse(inp.now);
  const h = fingerprint(inc.request).sha256;
  const row = inp.rows.find((r) => r.caller === caller && r.idempotency_key === inc.key);
  if (!row || now >= Date.parse(row.expires_at)) return { caller, outcome: "EXECUTE" };
  if (row.command !== inc.command || row.target !== inc.target || row.request_hash !== h)
    return { caller, outcome: "REJECT", code: "INVALID_ARGUMENT", http: 400, reason: "IDEMPOTENCY_MISMATCH" };
  if (row.status === "CLAIMED")
    return { caller, outcome: "REJECT", code: "ABORTED", http: 409, reason: "IDEMPOTENCY_IN_PROGRESS" };
  return { caller, outcome: "REPLAY", result: row.result };
}

function keys(op, inp) {
  if (op === "resolve_key") {
    if (inp.header != null && inp.body != null && inp.header !== inp.body)
      return { error: { reason: "IDEMPOTENCY_MISMATCH", code: "INVALID_ARGUMENT", http: 400 } };
    return { ok: { key: inp.header ?? inp.body ?? null } };
  }
  if (op === "caller_namespace") return { ok: { caller: ns(inp.caller) } };
  if (op === "expires_at") {
    const ms = Date.parse(inp.created_at) + 30 * 24 * 3600 * 1000;
    // microseconds survive: keep the fractional part of the input as text
    const frac = (inp.created_at.match(/\.(\d+)Z$/) || [])[1] || "";
    let s = new Date(ms).toISOString().replace(/\.\d{3}Z$/, "");
    const f = frac.replace(/0+$/, "");
    return { ok: { expires_at: s + (f ? "." + f : "") + "Z" } };
  }
  throw new Error(op);
}

for (const topic of ["fingerprint", "decide", "keys"]) {
  const doc = JSON.parse(readFileSync(join(dir, topic + ".json"), "utf8"));
  for (const c of doc.cases) {
    n++;
    let got, want;
    if (topic === "fingerprint") {
      got = fingerprint(c.input.json_text);
      want = c.expected_error ? { error: c.expected_error.reason } : c.expected;
    } else if (topic === "decide") {
      got = decide(c.input); want = c.expected;
    } else {
      const r = keys(c.op, c.input);
      got = r.error ? { error: r.error } : r.ok;
      want = c.expected_error ? { error: c.expected_error } : c.expected;
    }
    if (!isDeepStrictEqual(got, want)) {
      bad++;
      console.log(`DISAGREE ${c.id}: want ${JSON.stringify(want)} node got ${JSON.stringify(got)}`);
    }
  }
}
console.log(`idempotency xcheck: ${n} cases, ${bad} disagreements`);
process.exit(bad ? 1 : 0);
