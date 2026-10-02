// xcheck_redaction recomputes vectors/redaction/redact.json in Node with a
// character scanner for key words (the generator uses regular expressions).
//
//   docker run --rm -v "$PWD":/v:ro node:22-alpine node /v/redaction/gen/xcheck_redaction.mjs /v/redaction
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { isDeepStrictEqual } from "node:util";

const NAMES = [["phone"], ["mobile"], ["id", "card"], ["password"], ["bank", "card"], ["email"], ["token"], ["secret"],
  ["authorization"], ["cookie"], ["set", "cookie"], ["api", "key"]];
const ENVELOPE = new Set(["time", "level", "msg", "component_id", "component_version", "trace_id", "span_id", "request_id"]);
const isUp = (c) => c >= "A" && c <= "Z", isLow = (c) => (c >= "a" && c <= "z") || (c >= "0" && c <= "9");

function words(key) {
  const out = []; let cur = "";
  const cs = [...key];
  for (let i = 0; i < cs.length; i++) {
    const c = cs[i];
    if (c === "_" || c === "-" || c === ".") { if (cur) out.push(cur); cur = ""; continue; }
    const prev = cs[i - 1] ?? "", next = cs[i + 1] ?? "";
    // a boundary before an upper-case letter after a lower-case one, or
    // before the last capital of an acronym followed by a lower-case letter
    if (cur && isUp(c) && (isLow(prev) || (isUp(prev) && next >= "a" && next <= "z"))) { out.push(cur); cur = ""; }
    cur += c.toLowerCase();
  }
  if (cur) out.push(cur);
  return out;
}
function prot(key) {
  const w = words(key);
  return NAMES.some((nw) => {
    for (let i = 0; i + nw.length <= w.length; i++) {
      let ok = true;
      for (let j = 0; j < nw.length; j++) {
        const last = j === nw.length - 1;
        ok &&= w[i + j] === nw[j] || (last && w[i + j] === nw[j] + "s");
      }
      if (ok) return true;
    }
    return false;
  });
}
const walk = (v) => Array.isArray(v) ? v.map(walk)
  : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, prot(k) ? "[REDACTED]" : walk(x)])) : v;
const redact = (r) => Object.fromEntries(Object.entries(r).map(([k, x]) => [k, ENVELOPE.has(k) ? x : prot(k) ? "[REDACTED]" : walk(x)]));

let bad = 0, n = 0;
for (const c of JSON.parse(readFileSync(join(process.argv[2], "redact.json"), "utf8")).cases) {
  n++;
  const got = c.op === "redact" ? { record: redact(c.input.record) } : { protected: prot(c.input.key) };
  if (!isDeepStrictEqual(got, c.expected)) { bad++; console.log(`DISAGREE ${c.id}: want ${JSON.stringify(c.expected)}\n  node ${JSON.stringify(got)}`); }
}
console.log(`redaction xcheck: ${n} cases, ${bad} disagreements`);
process.exit(bad ? 1 : 0);
