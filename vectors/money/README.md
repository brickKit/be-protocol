[English](README.md) · [中文](README.zh.md)

# Vectors: money

Decimal strings, column capacity, minor units, rounding, allocation, tax, currency pairing and conversion (protocol P11.6). SDK API: the `money` package (Go `money.Parse`, `d.Round(scale, mode)`, `money.Amount`, `money.Allocate`, `money.ScaleOf`; Python `besdk.money`; TypeScript `@brickkit/be-sdk-ts/money`).

## Files

| File | Cases | Operations |
|---|---|---|
| `columns.json` | 9 | `column` |
| `currencies.json` | 45 | `minor_units` |
| `parse.json` | 57 | `parse` |
| `format.json` | 19 | `format` |
| `round.json` | 46 | `round`, `round_cash`, `round_qty` |
| `allocate.json` | 20 | `allocate` |
| `tax.json` | 13 | `tax_line`, `tax_document` |
| `arithmetic.json` | 31 | `add`, `sub`, `convert`, `line_amount` |
| `iso4217.json` | — | data: the minor-units table every SDK embeds (165 codes, ISO 4217 List One) |

## Operations

All values are decimal strings in and out; `mode` is optional and defaults to `HALF_AWAY_FROM_ZERO`.

| Op | Input | Expected |
|---|---|---|
| `column` | `kind`: amount, price, cost, quantity, rate, ratio, factor, currency | `sql`, `precision`, `scale`, `integer_digits` |
| `minor_units` | `currency` | `minor_units` |
| `parse` | `value`, `kind` (a column kind, or `decimal` for no capacity check) | `value`: normalised (no leading zeros, no trailing fractional zeros, no `-0`) |
| `format` | `value`, `currency` | `value` with exactly the currency's minor units; never rounds |
| `round` | `value`, `currency` or `scale`, `mode` | `value` at that scale |
| `round_cash` | `value`, `currency`, `increment` (`0.05`), `mode` | `value` rounded to a multiple of `increment`, written at the currency's minor units |
| `round_qty` | `value`, `rounding` (the unit's rounding, `0.001`, `1`), `mode` | `value` at the scale of `rounding` |
| `allocate` | `total`, `currency`, `weights[]` | `parts[]`, summing exactly to `total` |
| `tax_line` / `tax_document` | `lines[]` (net amounts), `rate` (ratio), `currency`, `mode` | `line_taxes[]`, `total` |
| `add` / `sub` | `a`, `b`: `{value, currency}` | `{value, currency}` |
| `convert` | `amount`: `{value, currency}`, `rate`, `to`, `mode` | `{value, currency}` in `to` |
| `line_amount` | `quantity`, `price`, `discount` (ratio), `currency`, `mode` | `{value, currency}` |

## Rules

- **Syntax**: `^-?[0-9]+(\.[0-9]+)?$` on the whole string; anything else (exponent, `+`, spaces, `NaN`, `Infinity`, separators, `1.`, `.5`, non-ASCII digits, JSON numbers, `null`) is `DECIMAL_SYNTAX`.
- **Capacity** (the column, foundations 06): amount `(19,4)`, price and cost and quantity `(19,6)`, rate `(19,10)`, ratio `(9,6)`, factor `(24,12)`. Integer digits above `precision − scale` are `DECIMAL_OVERFLOW`; significant decimals above `scale` are `DECIMAL_SCALE` (trailing zeros do not count).
- **An amount in a currency** may carry at most the currency's minor units (`12.345` CNY is `DECIMAL_SCALE`); `format` never rounds.
- **Rounding** is exact (no floating point): `HALF_AWAY_FROM_ZERO` (default) or `HALF_EVEN`, ties judged on the exact value. A result of zero is written without a sign.
- **Allocation**: share = total × weight ÷ Σweights, exactly; floor each share to minor units; give one minor unit to each of the shares with the largest remainders until the total is reached; equal remainders go to the earlier line. A negative total allocates its absolute value and negates every part. Weights are decimal strings ≥ 0 and must not all be zero.
- **Tax per line**: round each line's tax; the total is their sum. **Per document**: round the total once, then allocate it over the lines by their net amounts. The rate is a ratio in [0, 1].
- **Currency pairing**: `add` / `sub` of different currencies is `CURRENCY_MISMATCH`; a result beyond the amount column is `DECIMAL_OVERFLOW`.
- **Conversion**: `round(value × rate)` to the target's minor units; the rate is positive, at most 10 decimals, and exactly 1 when the currencies are equal.
- **Line amount**: `round(quantity × price × (1 − discount))`, rounded once at the end.
- **Currency codes**: three upper-case letters (`CURRENCY_INVALID` otherwise) present in `iso4217.json` (`CURRENCY_UNKNOWN` otherwise). Codes whose minor units are N.A. (XAU, XDR, XXX, XTS, …) are not in the table.

## Errors

Every class below surfaces as `INVALID_ARGUMENT` when it comes from request data, with the field in `violations[]`.

| Class | When |
|---|---|
| `DECIMAL_SYNTAX` | not a decimal string |
| `DECIMAL_OVERFLOW` | too many integer digits for the column |
| `DECIMAL_SCALE` | more decimals than the column or the currency allows |
| `CURRENCY_INVALID`, `CURRENCY_UNKNOWN` | bad or unknown currency code |
| `CURRENCY_MISMATCH` | arithmetic across currencies |
| `ALLOCATION_INVALID` | no weights, a negative weight, all weights zero |
| `RATE_INVALID`, `RATIO_INVALID` | rate ≤ 0 or ≠ 1 for the same currency; ratio outside [0, 1] |
| `ROUNDING_INVALID` | a rounding step ≤ 0, or a cash increment finer than the currency |
| `MODE_UNKNOWN`, `KIND_UNKNOWN` | unknown rounding mode or column kind |

## Decided here

The protocol fixes the column specs, the default mode and "largest remainder". These vectors also decide, for review: leading zeros are accepted on input (`007.50`); trailing zeros never count against a scale; negative totals are allocated on their absolute value; per-document tax allocates by net line amounts; `round_qty` takes the unit's rounding as a decimal step; same-currency conversion requires rate 1.

## Regenerate

`python3 gen/gen_money.py`; cross-check `go run gen/xcheck_money.go .` (see [../README.md](../README.md)). `gen/iso4217-list-one.xml` is the official list the table is built from; replace it with a newer publication to update `iso4217.json`.
