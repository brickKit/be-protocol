[English](README.md) · [中文](README.zh.md)

# Vectors: numbering

Document number formats (`<NAME>_NO_FORMAT`), the period a format resets on, and the allocation models of gap-free and gapped series (protocol P11.10; foundations 04). SDK API: Go `Series` and `tx.NextNumber(series)`, the same in Python and TypeScript; the `besdk_number_series` table (appendix A).

## Files

| File | Cases | Operations |
|---|---|---|
| `format.json` | 28 | `format_number` |
| `period.json` | 7 | `period_key` |
| `series.json` | 11 | `series_sim` |

## Operations

| Op | Input | Expected |
|---|---|---|
| `format_number` | `format`, `legal_entity_code`, `business_date`, `seq` | `number` |
| `period_key` | `format`, `business_date` | `period`: the `besdk_number_series.period` value a calendar-based series uses |
| `series_sim` | `mode` (`gapless` or `gapped`), `block_size` (gapped), `steps[]`: `{tx, op: alloc, scope, period[, process]}`, `{tx, op: commit}`, `{tx, op: rollback}`, `{op: crash, process}` | `committed[]` (`tx`, `scope`, `period`, `number` of every number that reached a commit), `series_rows[]` (`scope`, `period`, `next_value` left in the table) |

## Rules

- **Placeholders**: `{le}` (the legal entity's code, `[A-Za-z0-9_-]{1,32}`), `{yyyy}`, `{yy}`, `{mm}` (from the business date in the legal entity's zone), `{seq:N}` (zero-padded to N digits, N 1–18, written `5` or `05`). Nothing else: `{dd}`, `{seq}`, `{YYYY}`, a stray brace, whitespace or a control character in the literal text is `FORMAT_INVALID`. Literal text may be any other character, CJK included (`记-`).
- **Exactly one `{seq:N}`**: none is `FORMAT_NO_SEQUENCE`, two are `FORMAT_INVALID`.
- **A sequence wider than N** is written in full, never truncated.
- **The period a format resets on** follows from its finest date placeholder: `{mm}` → monthly, period `YYYY-MM`; only `{yyyy}` / `{yy}` → yearly, period `YYYY`; none → never, period empty. A monthly format must also carry the year, or its numbers repeat a year later: `FORMAT_REPEATS`. The legal entity is the series' `scope`, so `{le}` in the number is optional.
- **Gap-free series** (vouchers): allocation locks the series row in the business transaction; transactions are therefore serial per (series, scope, period); a rollback undoes the increment, so committed numbers are continuous. Voucher series are keyed by the fiscal `period_key` (`2026-P07`, calendar vectors).
- **Gapped series**: each process reserves a block of `block_size` numbers in its own short committed transaction and hands them out from memory; rollbacks and crashes leave gaps; numbers are unique, increasing within one process, not across processes.
- A gap-free number is allocated only after the idempotency claim succeeded (P13.5), so a replay never consumes one.
- **Uniqueness** is not a property of these simulations: the runtime records every formatted number in `besdk_number_allocations` (primary key `(legal_entity_id, series, number)`, unpartitioned) in the document's transaction, so a repeat fails that transaction (P11.10).

## Errors

| Class | When |
|---|---|
| `FORMAT_INVALID` | unknown placeholder, bad width, braces or whitespace in the literal, two sequences, empty format |
| `FORMAT_NO_SEQUENCE` | no `{seq:N}` |
| `FORMAT_REPEATS` | monthly reset without a year |
| `SEQ_INVALID` | a sequence below 1 |
| `LEGAL_ENTITY_CODE_INVALID` | `{le}` value with characters outside `[A-Za-z0-9_-]` or longer than 32 |

All of these are configuration errors when they come from `<NAME>_NO_FORMAT`: the component stops at start with exit code 78 and names the key.

## Decided here

For review: the width is written `N` or `0N` (the documented default `{seq:05}` uses the second form); a wider sequence widens; the period key is derived from the format's placeholders; monthly formats without a year are rejected; `{le}` uses the legal entity's code, not its id; the gapped block size is an SDK parameter, not a protocol constant.

## Regenerate

`python3 gen/gen_numbering.py`; cross-check `node gen/xcheck_numbering.mjs .`.
