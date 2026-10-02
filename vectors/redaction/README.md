[English](README.md) · [中文](README.zh.md)

# Vectors: redaction

Which log field keys carry personal data, and what the SDK's log handler writes instead (protocol P18.2; foundations 23). SDK API: none for components: every SDK applies this inside its log handler, before a line is written, so business code never calls it.

## Files

| File | Cases | Operations |
|---|---|---|
| `redact.json` | 29 | `redact`, `protected_key` |

## Operations

| Op | Input | Expected |
|---|---|---|
| `redact` | `record`: one log record as a JSON object (envelope fields plus the call's fields) | `record` as written |
| `protected_key` | `key` | `protected`: `true` or `false` |

## Rules

- **Protected names**: `phone`, `mobile`, `id_card`, `password`, `bank_card`, `email`, `token`, `secret`, `authorization`, `cookie`, `set_cookie`, `api_key` (P18.2; `Set-Cookie`, `X-Api-Key` and `apiKey` match through the key-word rule).
- **Key words**: split camelCase (`contactPhone` → `contact`, `phone`; `IDCard` → `id`, `card`), treat `-` and `.` like `_`, lower-case, split on `_`.
- **Match**: the protected name's words appear in the key's words as one contiguous run; the last word may carry a plural `s`. So `phone_number`, `access_token`, `user.email`, `old_bank_card_tail`, `emails` match; `telephone`, `tokenizer`, `card`, `id` do not.
- **Replacement**: the matching field's value, of any type (string, number, boolean, null, object, array), becomes the string `[REDACTED]`; it is not walked further.
- **Recursion**: a non-matching object or array is walked, and the rule applies to every key inside.
- **Envelope fields** (`time`, `level`, `msg`, `component_id`, `component_version`, `trace_id`, `span_id`, `request_id`) are never touched.
- **Values are never scanned**: a phone number inside `msg` or `note` stays. Code must not put personal data into free text.

## Errors

None: redaction never fails.

## Decided here

For review: matching by whole words with a plural `s` (P18.2 lists the names, not the matching rule; exact-name matching would miss `phone_number` and `access_token`, the most common forms); over-redaction of harmless keys such as `token_type` or `phone_verified` is accepted. These semantics are normative (P18.2). Not covered here: the 2 KiB line truncation (P18.2 states it: the line stays valid JSON, string values cut longest first with `…[TRUNCATED]`, `truncated: true` added), which depends on each language's JSON encoder and so has no byte-exact vectors; the `error` field's text is a value and is not scanned.

## Regenerate

`python3 gen/gen_redaction.py`; cross-check `node gen/xcheck_redaction.mjs .`.
