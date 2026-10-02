// xcheck_numbering recomputes vectors/numbering/*.json in Node with a
// character-by-character format scanner (the generator uses a regex
// tokenizer) and its own allocation model.
//
//   docker run --rm -v "$PWD":/v:ro node:22-alpine node /v/numbering/gen/xcheck_numbering.mjs /v/numbering
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { isDeepStrictEqual } from "node:util";

const dir = process.argv[2];
class E extends Error { constructor(r) { super(r); this.reason = r; } }

function scan(f) {
  if (typeof f !== "string" || f.length === 0) throw new E("FORMAT_INVALID");
  const parts = []; let lit = "", i = 0, seqs = 0;
  const chars = Array.from(f);
  while (i < chars.length) {
    const ch = chars[i];
    if (ch === "}") throw new E("FORMAT_INVALID");
    if (ch === "{") {
      const close = chars.indexOf("}", i);
      const nextOpen = chars.indexOf("{", i + 1);
      if (close < 0 || (nextOpen >= 0 && nextOpen < close)) throw new E("FORMAT_INVALID");
      if (lit) { parts.push({ k: "lit", v: lit }); lit = ""; }
      const name = chars.slice(i + 1, close).join("");
      if (["le", "yyyy", "yy", "mm"].includes(name)) parts.push({ k: name });
      else if (name.startsWith("seq:") && /^[0-9]{1,2}$/.test(name.slice(4)) && +name.slice(4) >= 1 && +name.slice(4) <= 18) {
        parts.push({ k: "seq", w: +name.slice(4) }); seqs++;
      } else throw new E("FORMAT_INVALID");
      i = close + 1; continue;
    }
    const cp = ch.codePointAt(0);
    if (cp < 0x20 || cp === 0x7f || /\s/u.test(ch)) throw new E("FORMAT_INVALID");
    lit += ch; i++;
  }
  if (lit) parts.push({ k: "lit", v: lit });
  if (seqs === 0) throw new E("FORMAT_NO_SEQUENCE");
  if (seqs > 1) throw new E("FORMAT_INVALID");
  const has = (k) => parts.some((p) => p.k === k);
  if (has("mm") && !has("yyyy") && !has("yy")) throw new E("FORMAT_REPEATS");
  return { parts, gran: has("mm") ? "month" : has("yyyy") || has("yy") ? "year" : "none" };
}
function render({ format, legal_entity_code: le, business_date: d, seq }) {
  const { parts } = scan(format);
  if (!Number.isInteger(seq) || seq < 1) throw new E("SEQ_INVALID");
  if (typeof le !== "string" || !/^[A-Za-z0-9_-]{1,32}$/.test(le)) throw new E("LEGAL_ENTITY_CODE_INVALID");
  const [y, m] = d.split("-");
  return parts.map((p) => p.k === "lit" ? p.v : p.k === "le" ? le : p.k === "yyyy" ? y : p.k === "yy" ? y.slice(2)
    : p.k === "mm" ? m : String(seq).padStart(p.w, "0")).join("");
}
function sim({ mode, steps, block_size }) {
  const rows = new Map(), blocks = new Map(), open = new Map(), committed = [];
  const key = (s) => s.scope + "\u0000" + s.period;
  for (const s of steps) {
    if (s.op === "alloc") {
      const k = key(s); let n;
      if (mode === "gapless") { n = rows.get(k) ?? 1; rows.set(k, n + 1); }
      else {
        const bk = s.process + "\u0000" + k; let b = blocks.get(bk);
        if (!b || b.next === b.end) { const st = rows.get(k) ?? 1; rows.set(k, st + block_size); b = { next: st, end: st + block_size }; blocks.set(bk, b); }
        n = b.next++;
      }
      if (!open.has(s.tx)) open.set(s.tx, []);
      open.get(s.tx).push({ scope: s.scope, period: s.period, n });
    } else if (s.op === "commit") {
      for (const a of open.get(s.tx) ?? []) committed.push({ tx: s.tx, scope: a.scope, period: a.period, number: a.n });
      open.delete(s.tx);
    } else if (s.op === "rollback") {
      if (mode === "gapless") for (const a of open.get(s.tx) ?? []) rows.set(key(a), rows.get(key(a)) - 1);
      open.delete(s.tx);
    } else if (s.op === "crash") {
      for (const k of [...blocks.keys()]) if (k.startsWith(s.process + "\u0000")) blocks.delete(k);
    }
  }
  const series_rows = [...rows.entries()].map(([k, v]) => { const [scope, period] = k.split("\u0000"); return { scope, period, next_value: v }; })
    .sort((a, b) => (a.scope + a.period < b.scope + b.period ? -1 : 1));
  return { committed, series_rows };
}
function run(op, i) {
  if (op === "format_number") return { number: render(i) };
  if (op === "period_key") {
    const { gran } = scan(i.format), [y, m] = i.business_date.split("-");
    return { period: gran === "month" ? `${y}-${m}` : gran === "year" ? y : "" };
  }
  if (op === "series_sim") return sim(i);
  throw new Error(op);
}
let bad = 0, n = 0;
for (const t of ["format", "period", "series"]) {
  for (const c of JSON.parse(readFileSync(join(dir, t + ".json"), "utf8")).cases) {
    n++;
    let got;
    try { got = run(c.op, c.input); } catch (e) { if (!(e instanceof E)) throw e; got = { reason: e.reason }; }
    const want = c.expected ?? c.expected_error;
    if (!isDeepStrictEqual(got, want)) { bad++; console.log(`DISAGREE ${c.id}: want ${JSON.stringify(want)} node got ${JSON.stringify(got)}`); }
  }
}
console.log(`numbering xcheck: ${n} cases, ${bad} disagreements`);
process.exit(bad ? 1 : 0);
