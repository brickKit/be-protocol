// xcheck_calendar recomputes vectors/calendar/*.json with Node's Intl (ICU
// time-zone data), independently of the Python zoneinfo generator.
//
//   docker run --rm -v "$PWD":/v:ro node:22-alpine node /v/calendar/gen/xcheck_calendar.mjs /v/calendar
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { isDeepStrictEqual } from "node:util";

const dir = process.argv[2];
class E extends Error { constructor(r) { super(r); this.reason = r; } }
const fmts = new Map();
function zone(name) {
  if (typeof name !== "string" || !/^(UTC|[A-Z][A-Za-z_]+(\/[A-Z0-9][A-Za-z0-9_+-]*)+)$/.test(name)) throw new E("TZ_UNKNOWN");
  if (!fmts.has(name)) {
    try {
      fmts.set(name, new Intl.DateTimeFormat("en-CA", { timeZone: name, year: "numeric", month: "2-digit", day: "2-digit", hourCycle: "h23" }));
    } catch { throw new E("TZ_UNKNOWN"); }
  }
  return fmts.get(name);
}
const civil = (f, ms) => {
  const p = Object.fromEntries(f.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}`;
};
function parseDate(s) {
  if (typeof s !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(s)) throw new E("DATE_INVALID");
  const [y, m, d] = s.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d));
  if (t.getUTCFullYear() !== y || t.getUTCMonth() !== m - 1 || t.getUTCDate() !== d) throw new E("DATE_INVALID");
  return { y, m, d };
}
const iso = ({ y, m, d }) => `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
const nextDay = ({ y, m, d }) => { const t = new Date(Date.UTC(y, m - 1, d + 1)); return { y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate() }; };
function instant(s) {
  if (typeof s !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$/.test(s)) throw new E("INSTANT_INVALID");
  return Date.parse(s); // sub-millisecond digits do not change the date in any zone used here
}
const fmtInst = (ms) => new Date(ms).toISOString().replace(".000Z", "Z");
// first instant (whole seconds) whose civil date is >= date
function dayStart(dateObj, f) {
  const target = iso(dateObj);
  let lo = Date.UTC(dateObj.y, dateObj.m - 1, dateObj.d) / 1000 - 20 * 3600, hi = lo + 48 * 3600;
  while (hi - lo > 1) { const mid = Math.floor((lo + hi) / 2); if (civil(f, mid * 1000) >= target) hi = mid; else lo = mid; }
  return hi * 1000;
}
function periodOf(dObj, s) {
  if (!Number.isInteger(s) || s < 1 || s > 12) throw new E("FISCAL_START_INVALID");
  const { y, m } = dObj;
  const fy = m >= s ? y : y - 1, p = ((m - s + 12) % 12) + 1;
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const mm = String(m).padStart(2, "0");
  return { fiscal_year: fy, fiscal_year_label: s === 1 ? String(fy) : `${fy}/${String((fy + 1) % 100).padStart(2, "0")}`,
    period: p, period_key: `${fy}-P${String(p).padStart(2, "0")}`, start_date: `${y}-${mm}-01`, end_date: `${y}-${mm}-${last}`, label: `${y}-${mm}` };
}
function run(op, i) {
  switch (op) {
    case "business_date": { const ms = instant(i.instant); return { date: civil(zone(i.time_zone), ms) }; }
    case "parse_date": return { date: iso(parseDate(i.value)) };
    case "day_bounds": {
      const d = parseDate(i.date), f = zone(i.time_zone), st = dayStart(d, f);
      if (civil(f, st) !== iso(d)) throw new E("DATE_NONEXISTENT");
      const en = dayStart(nextDay(d), f);
      return { start: fmtInst(st), end: fmtInst(en), hours: (en - st) / 3600000 };
    }
    case "date_range": {
      const a = parseDate(i.first), b = parseDate(i.last);
      if (iso(b) < iso(a)) throw new E("RANGE_INVALID");
      const f = zone(i.time_zone);
      return { start: fmtInst(dayStart(a, f)), end: fmtInst(dayStart(nextDay(b), f)) };
    }
    case "fiscal_period": return periodOf(parseDate(i.date), i.start_month);
    case "fiscal_year": {
      if (!Number.isInteger(i.start_month) || i.start_month < 1 || i.start_month > 12) throw new E("FISCAL_START_INVALID");
      const periods = [];
      for (let k = 0; k < 12; k++) {
        const mi = i.start_month - 1 + k, y = i.fiscal_year + Math.floor(mi / 12), m = (mi % 12) + 1;
        const { period, period_key, start_date, end_date, label } = periodOf({ y, m, d: 1 }, i.start_month);
        periods.push({ period, period_key, start_date, end_date, label });
      }
      return { fiscal_year: i.fiscal_year, start_date: periods[0].start_date, end_date: periods[11].end_date, periods };
    }
  }
  throw new Error(op);
}
let bad = 0, n = 0;
for (const t of ["business_date", "bounds", "fiscal"]) {
  for (const c of JSON.parse(readFileSync(join(dir, t + ".json"), "utf8")).cases) {
    n++;
    let got;
    try { got = run(c.op, c.input); } catch (e) { if (!(e instanceof E)) throw e; got = { reason: e.reason }; }
    const want = c.expected ?? c.expected_error;
    if (!isDeepStrictEqual(got, want)) { bad++; console.log(`DISAGREE ${c.id}: want ${JSON.stringify(want)} node got ${JSON.stringify(got)}`); }
  }
}
console.log(`calendar xcheck: ${n} cases, ${bad} disagreements (node tz ${process.versions.tz})`);
process.exit(bad ? 1 : 0);
