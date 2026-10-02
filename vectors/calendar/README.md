[English](README.md) · [中文](README.zh.md)

# Vectors: calendar

Business dates from instants in a legal entity's time zone, the instant bounds of a day or a date range, and month-based fiscal periods and years (protocol P11.7, P11.9; foundations 05). SDK API: Go `Calendar.BusinessDate` / `Today` / `FiscalPeriod` and `Date`, the same in Python and TypeScript.

## Files

| File | Cases | Operations |
|---|---|---|
| `business_date.json` | 46 | `business_date` |
| `bounds.json` | 29 | `day_bounds`, `date_range`, `parse_date` |
| `fiscal.json` | 18 | `fiscal_period`, `fiscal_year` |

Each file's `notes.tzdata` names the tz database release the expected values were computed with (2026c).

## Operations

| Op | Input | Expected |
|---|---|---|
| `business_date` | `instant` (RFC 3339 UTC with `Z`), `time_zone` (IANA name) | `date` (`YYYY-MM-DD`) |
| `day_bounds` | `date`, `time_zone` | `start`, `end`: the half-open instant range of that civil day, and `hours` (23, 24 or 25 …) |
| `date_range` | `first`, `last`, `time_zone` | `start` = start of `first`, `end` = start of the day after `last` |
| `parse_date` | `value` | `date` |
| `fiscal_period` | `date`, `start_month` (1–12) | `fiscal_year`, `fiscal_year_label`, `period` (1–12), `period_key`, `start_date`, `end_date`, `label` |
| `fiscal_year` | `fiscal_year`, `start_month` | `start_date`, `end_date`, `periods[]` (12 entries) |

## Rules

- **Business date** = the civil date of the instant in the zone. Never ask the database; never compare a `DATE` with a `timestamptz`.
- **Start of a day** = the first instant whose civil date is that day. It is not always local midnight: when DST begins at midnight (São Paulo, 2018-11-04) the day starts at 01:00. A day can last 23 or 25 hours. A civil date that a zone skipped (Apia, 2011-12-30) has no bounds: `DATE_NONEXISTENT`.
- **Instants on input** are RFC 3339 UTC with `Z` (up to 6 fractional digits); an offset, a local time or a bare date is `INSTANT_INVALID`.
- **Zones** are IANA names, exact and case-sensitive, in the form `UTC` or `Area/Location`. Offsets (`+08:00`), `UTC+8`, unknown names and wrong case are `TZ_UNKNOWN`. `Etc/GMT-8` is valid and means UTC+8 (the POSIX sign is inverted). Link names (`Asia/Calcutta`) are deliberately absent: whether they exist depends on the installed tz database (they are missing on Debian/Ubuntu without `tzdata-legacy`), so legal entities store canonical names and each SDK embeds its tz data (Go `time/tzdata`, Python `tzdata`, Node full ICU).
- **Business dates on input** are `YYYY-MM-DD` exactly; anything else, or a date that does not exist, is `DATE_INVALID`.
- **Fiscal year** = the calendar year in which it starts. With start month `s`, a date in month `m` falls in period `(m − s) mod 12 + 1` of fiscal year `y` if `m ≥ s`, else `y − 1`. `period_key` = `<fiscal year>-P<NN>` (`2026-P07`); `label` = the calendar month (`2026-10`), display only; `fiscal_year_label` = `2026` for a January start, else `2026/27`.

## Errors

| Class | When |
|---|---|
| `TZ_UNKNOWN` | the zone is not an IANA name known to the tz database |
| `INSTANT_INVALID`, `DATE_INVALID` | malformed or non-existent input |
| `DATE_NONEXISTENT` | the civil date was skipped in that zone |
| `RANGE_INVALID` | `last` before `first` |
| `FISCAL_START_INVALID` | start month outside 1–12 |

## Decided here

For review: the fiscal year is named by its starting calendar year, `period_key` uses the `-Pnn` form so it can never be mistaken for a calendar month, and `fiscal_year_label` uses `YYYY/YY`. Instants are second-accurate for bounds (no zone changes offset at a fractional second).

## Regenerate

`python3 gen/gen_calendar.py` (needs the system tz database; the release is recorded in the files); cross-check `node gen/xcheck_calendar.mjs .` (ICU). Both sides must use the same tz release; when the release changes, regenerate and cross-check together.
