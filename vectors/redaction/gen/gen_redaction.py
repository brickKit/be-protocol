#!/usr/bin/env python3
"""Generate vectors/redaction/redact.json (protocol P18.2; foundations 23).

Personal data in log fields is redacted by key, in the SDK's log handler,
before the line is written. Rule (see README.md):

1. normalise the key: split camelCase (fooBar -> foo_Bar, IDCard -> ID_Card),
   turn '-' and '.' into '_', lower-case it, split into words on '_';
2. the key matches a protected name when the name's words appear in the key's
   words as one contiguous run; a final 's' on the key's last matching word is
   allowed (emails, tokens);
3. a matching field's value, whatever its type, becomes the string
   "[REDACTED]"; a non-matching object or array is walked recursively;
4. values are never scanned, and the envelope fields are never touched.
xcheck_redaction.mjs recomputes every case in Node.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_lib"))
from vecfile import CaseList, area_dir, write_file  # noqa: E402

GEN = "redaction/gen/gen_redaction.py"
OUT = area_dir(__file__)
NAMES = ["phone", "mobile", "id_card", "password", "bank_card", "email", "token", "secret",
         "authorization", "cookie", "set_cookie", "api_key"]
ENVELOPE = {"time", "level", "msg", "component_id", "component_version", "trace_id", "span_id", "request_id"}
MARK = "[REDACTED]"


def words(key):
    k = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    k = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", k)
    k = k.replace("-", "_").replace(".", "_").lower()
    return [w for w in k.split("_") if w]


def protected(key):
    ws = words(key)
    for name in NAMES:
        nw = name.split("_")
        for i in range(len(ws) - len(nw) + 1):
            run = ws[i:i + len(nw)]
            if run[:-1] == nw[:-1] and run[-1] in (nw[-1], nw[-1] + "s"):
                return True
    return False


def walk(v):
    if isinstance(v, dict):
        return {k: (MARK if protected(k) else walk(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [walk(x) for x in v]
    return v


def redact(record):
    return {k: (x if k in ENVELOPE else MARK if protected(k) else walk(x)) for k, x in record.items()}


def gen():
    c = CaseList("redaction", "redact")
    base = {"time": "2026-10-02T08:00:00.123456789Z", "level": "info", "msg": "owner_profile_updated",
            "component_id": "conformance/widget", "component_version": "1.0.0",
            "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736", "span_id": "00f067aa0ba902b7", "request_id": "r-1"}
    rows = [
        ("each-name", "every protected name", {n: "v-" + n for n in NAMES}),
        ("non-string-values", "numbers, booleans, null, objects and arrays are replaced too",
         {"phone": 13800138000, "token": None, "secret": {"a": 1}, "email": ["a@x.cn", "b@x.cn"], "password": True}),
        ("suffix", "a protected name as the last word", {"contact_phone": "1", "access_token": "2", "client_secret": "3",
                                                         "new_password": "4", "user_email": "5"}),
        ("prefix", "a protected name as the first word", {"phone_number": "1", "email_address": "2", "token_type": "Bearer",
                                                          "password_hash": "x", "id_card_no": "y"}),
        ("middle", "a protected name in the middle", {"primary_email_address": "1", "old_bank_card_tail": "2"}),
        ("plural", "a plural last word", {"emails": ["a@x.cn"], "tokens": 2, "phones": []}),
        ("camel-case", "camelCase keys", {"contactPhone": "1", "accessToken": "2", "idCard": "3", "bankCard": "4",
                                          "IDCard": "5", "userEMail": "6"}),
        ("kebab-and-dots", "kebab-case and dotted (OTel-style) keys", {"x-api-token": "1", "user.email": "2", "user.phone.number": "3"}),
        ("upper-case", "case does not matter", {"PHONE": "1", "Email": "2", "SECRET_KEY": "3"}),
        ("not-a-word", "the name inside a longer word does not match", {"telephone": "1", "emailer_count": 2, "tokenizer": "x",
                                                                       "secretary": "y", "mobilephone": "z", "passwordless": "p"}),
        ("half-of-two-words", "id or card alone is not id_card", {"id": "0192", "card": "visa", "bank": "ICBC",
                                                                  "card_bank": "x", "id_number_card": "y"}),
        ("nested", "nested objects and arrays are walked",
         {"user": {"name": "A", "mobile": "1", "contacts": [{"email": "a@x.cn", "label": "work"}, {"phone": "2"}]},
          "items": [[{"token": "t"}]]}),
        ("protected-object", "a protected key's whole object is replaced, not walked",
         {"secret": {"name": "visible?", "inner": {"x": 1}}}),
        ("envelope-untouched", "envelope fields are never redacted, even when the message mentions a name",
         {"msg": "phone 13800138000 changed"}),
        ("values-not-scanned", "values are not scanned for personal data", {"note": "call 13800138000 or a@x.cn"}),
        ("error-field", "the error text is not scanned; error.* sub-keys follow the rule",
         {"error": "token expired for a@x.cn", "error.code": "UNAUTHENTICATED", "error.reason": "TOKEN_INVALID"}),
        ("transport-secrets", "authorization, cookie, set-cookie and api_key in their usual spellings",
         {"authorization": "Bearer eyJ", "Cookie": "sid=1", "set-cookie": "sid=2; HttpOnly", "x-api-key": "k1",
          "apiKey": "k2", "API_KEY": "k3", "proxy_authorization": "Basic x"}),
        ("transport-near-misses", "api or key alone and cookie inside a longer word (cookiejar) do not match; cookies_count does, by the plural rule (accepted over-redaction)",
         {"api": "v2", "key": "conformance.widget.view", "cookies_count": 2, "cookiejar": "x", "authorized": True}),
        ("empty", "nothing to redact", {}),
    ]
    for slug, why, fields in rows:
        rec = dict(base, **fields)
        c.add(slug, why, "redact", {"record": rec}, expected={"record": redact(rec)}, refs=["P18.2"])
    for slug, key in [("key-phone-verified", "phone_verified"), ("key-next-page-token", "next_page_token"),
                      ("key-password-reset-at", "password_reset_at"), ("key-tokens-used", "tokens_used"),
                      ("key-authorization", "authorization"), ("key-cookie", "cookie"), ("key-api-key", "api_key"),
                      ("key-set-cookie", "Set-Cookie"), ("key-api-key-header", "X-Api-Key"), ("key-api-version", "api_version")]:
        c.add(slug, f"is {key!r} protected?", "protected_key", {"key": key}, expected={"protected": protected(key)}, refs=["P18.2"])
    return c


def main():
    n = write_file(os.path.join(OUT, "redact.json"), "redaction", "redact", GEN, gen())
    print("redaction", {"redact": n}, "total", n)


if __name__ == "__main__":
    main()
