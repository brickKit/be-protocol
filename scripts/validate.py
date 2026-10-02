#!/usr/bin/env python3
"""Static validation of be-protocol (make validate; runs in a throwaway python container).

1. Every JSON Schema in schemas/ (and vectors/case-file.schema.json) is a valid 2020-12 schema;
   every schema's own `examples` validate.
2. The catalogues validate: errors-be.yaml, config-keys.yaml, conformance-cases.yaml.
3. scripts/examples/: each sample validates, or is rejected when its name says `bad`.
4. Every reason of domain `be` yields a valid problem body (reasons of code INTERNAL are never
   shown to a caller and are skipped); every envelope vector's expected header set validates.
5. Every vector file validates against vectors/case-file.schema.json.
6. The fixtures: widget and peer contracts, fixtures.yaml, lifecycle.yaml, assembly.yaml, the
   events files, and the payload samples against their event payload schemas.
7. Tables that must agree: errors-be.yaml == the reason table of spec/04 (en and zh) == the
   BE_REASONS table of the errors vector generator; config-keys.yaml == the key table of spec/02,
   same order, en and zh.
8. Documents: every X.md has X.zh.md with the same number of `##` sections and requirement rows;
   relative links and anchors resolve.
Exit 1 when anything fails; every failure is printed.
"""
import glob
import json
import os
import re
import sys

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "schemas")
EX = os.path.join(ROOT, "scripts", "examples")
failures = []


def bad(msg):
    failures.append(msg)
    print("FAIL", msg)


def rel(p):
    return os.path.relpath(p, ROOT)


def load(p):
    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh) if p.endswith((".yaml", ".yml")) else json.load(fh)


# 1. schemas
schemas = {}
for f in sorted(glob.glob(os.path.join(S, "*.json"))) + [os.path.join(ROOT, "vectors", "case-file.schema.json")]:
    try:
        d = load(f)
        Draft202012Validator.check_schema(d)
    except Exception as e:  # noqa: BLE001
        bad(f"{rel(f)}: {getattr(e, 'message', e)}")
        continue
    schemas[os.path.basename(f)] = d
reg = Registry()
for name, d in schemas.items():
    r = Resource.from_contents(d)
    reg = reg.with_resource(d.get("$id", name), r).with_resource(name, r)


def validator(name):
    return Draft202012Validator(schemas[name], registry=reg, format_checker=Draft202012Validator.FORMAT_CHECKER)


def check(name, inst, where, expect_ok=True):
    errs = list(validator(name).iter_errors(inst))
    if bool(errs) == expect_ok:
        detail = "; ".join(f"{e.message[:160]} @{'/'.join(map(str, e.absolute_path))}" for e in errs[:3]) or "no errors"
        bad(f"{where} vs {name}: expected {'valid' if expect_ok else 'invalid'}: {detail}")
    return not errs


for name, d in schemas.items():
    for i, e in enumerate(d.get("examples", [])):
        check(name, e, f"{name} example {i}")

# 2. catalogues
be = load(os.path.join(S, "errors-be.yaml"))
check("errors-yaml.schema.json", be, "schemas/errors-be.yaml")
keys = load(os.path.join(S, "config-keys.yaml"))
check("config-keys.schema.json", keys, "schemas/config-keys.yaml")
cases = load(os.path.join(S, "conformance-cases.yaml"))
check("conformance-cases.schema.json", cases, "schemas/conformance-cases.yaml")

# 3. examples
for schema, f in [("lifecycle.schema.json", "lifecycle-sales.yaml"), ("lifecycle.schema.json", "lifecycle-finance.yaml"),
                  ("lifecycle.schema.json", "lifecycle-bad-ledger-pii.yaml"), ("lifecycle.schema.json", "lifecycle-bad-queue-cold.yaml"),
                  ("assembly-protocol.schema.json", "assembly.yaml"), ("fixtures.schema.json", "fixtures.yaml"),
                  ("info.schema.json", "info.json"), ("info.schema.json", "info-shell.json"),
                  ("problem.schema.json", "problem.json"), ("problem.schema.json", "problem-bad-internal.json"),
                  ("events-contract.schema.json", "events.json"), ("compconf-report.schema.json", "report.json"),
                  ("data-lifecycle-config.schema.json", "data-lifecycle.yaml"), ("jobs-overrides.schema.json", "jobs.json")]:
    check(schema, load(os.path.join(EX, f)), f"scripts/examples/{f}", expect_ok="-bad-" not in f)

# 4. be reasons as problem bodies; envelope header sets
hidden = {"INTERNAL", "UNKNOWN", "DATA_LOSS"}
for r in be["reasons"]:
    if r["code"] in hidden and r["reason"] != "INTERNAL":
        continue
    body = {"type": f"urn:be:be:{r['reason']}", "title": r["title"]["en"], "status": r["http"], "code": r["code"],
            "reason": r["reason"], "domain": "be", "detail": "x", "metadata": {p: "v" for p in r["params"]},
            "instance": "/x", "request_id": "r", "trace_id": "0" * 32}
    check("problem.schema.json", body, f"problem body for {r['reason']}")
n_headers = 0
for f in sorted(glob.glob(os.path.join(ROOT, "vectors", "envelope", "*.json"))):
    for c in load(f).get("cases", []):
        h = (c.get("expected") or {}).get("headers")
        if isinstance(h, dict):
            n_headers += 1
            check("envelope.schema.json", h, f"envelope vector {c['id']}")

# 5. vector files
vector_files = [f for f in sorted(glob.glob(os.path.join(ROOT, "vectors", "*", "*.json"))) if not f.endswith("iso4217.json")]
for f in vector_files:
    check("case-file.schema.json", load(f), rel(f))

# 6. fixtures
W = os.path.join(ROOT, "fixtures", "widget")
Q = os.path.join(ROOT, "fixtures", "peer")
for schema, f in [("fixtures.schema.json", f"{W}/conformance/fixtures.yaml"),
                  ("errors-yaml.schema.json", f"{W}/contracts/errors.yaml"),
                  ("errors-yaml.schema.json", f"{Q}/contracts/errors.yaml"),
                  ("lifecycle.schema.json", f"{W}/migrations/lifecycle.yaml"),
                  ("assembly-protocol.schema.json", f"{W}/assembly.yaml"),
                  ("events-contract.schema.json", f"{W}/contracts/events/widget.events.json"),
                  ("events-contract.schema.json", f"{Q}/contracts/events/peer.events.json")]:
    check(schema, load(f), rel(f))
samples = {"conformance.owner.updated.v1": "owner-updated.json", "conformance.reservation.expired.v1": "reservation-expired.json"}
for ev in load(f"{Q}/contracts/events/peer.events.json")["events"]:
    if ev["subject"] in samples:
        doc = load(f"{W}/conformance/samples/{samples[ev['subject']]}")
        errs = list(Draft202012Validator(ev["payload"]).iter_errors(doc))
        if errs:
            bad(f"sample {samples[ev['subject']]} vs payload of {ev['subject']}: {errs[0].message}")
fx = load(f"{W}/conformance/fixtures.yaml")
for consumed in fx["events"]["consumes"]:
    if not os.path.exists(os.path.join(W, "conformance", consumed["sample_file"])):
        bad(f"fixtures.yaml: missing sample {consumed['sample_file']}")


# 7. tables that must agree
def reason_rows(path):
    t = open(path, encoding="utf-8").read()
    t = t[t.index("| `INTERNAL` | `INTERNAL` |"):]
    return dict(re.findall(r"^\| `([A-Z_]+)` \| `([A-Z_]+)` \|", t, re.M))


be_map = {r["reason"]: r["code"] for r in be["reasons"]}
for lang in ("", ".zh"):
    spec_map = reason_rows(os.path.join(ROOT, "spec", f"04-errors{lang}.md"))
    if spec_map != be_map:
        bad(f"spec/04-errors{lang}.md reason table != errors-be.yaml: only in spec {sorted(set(spec_map) - set(be_map))}, "
            f"only in yaml {sorted(set(be_map) - set(spec_map))}, code diffs {[k for k in be_map if k in spec_map and spec_map[k] != be_map[k]]}")
gen = open(os.path.join(ROOT, "vectors", "errors", "gen", "gen_errors.py"), encoding="utf-8").read()
gen_tab = gen[gen.index("BE_REASONS = {"):]
gen_tab = dict(re.findall(r'"([A-Z_]+)": "([A-Z_]+)"', gen_tab[:gen_tab.index("}")]))
if gen_tab != be_map:
    bad(f"vectors/errors/gen/gen_errors.py BE_REASONS != errors-be.yaml: {sorted(set(gen_tab) ^ set(be_map))}")
cat_keys = [k["name"] for k in keys["keys"]]
for lang in ("", ".zh"):
    t = open(os.path.join(ROOT, "spec", f"02-configuration{lang}.md"), encoding="utf-8").read()
    rows = [k for k in re.findall(r"^\| `([A-Z0-9_]+)` \|", t, re.M) if k in set(cat_keys)]
    if rows[:len(cat_keys)] != cat_keys:
        bad(f"spec/02-configuration{lang}.md key table != config-keys.yaml (order included): {sorted(set(cat_keys) - set(rows))}")


# 8. documents
def slug(h):
    s = re.sub(r"[^\w\- 一-鿿]", "", h.strip().lower())
    return s.replace(" ", "-")


docs = [f for f in glob.glob(os.path.join(ROOT, "**", "*.md"), recursive=True) if "/.git/" not in f]
for en in sorted(d for d in docs if not d.endswith(".zh.md")):
    zh = en[:-3] + ".zh.md"
    if not os.path.exists(zh):
        bad(f"{rel(en)} has no Chinese mirror")
        continue
    E, Z = open(en, encoding="utf-8").read(), open(zh, encoding="utf-8").read()
    if len(re.findall(r"^## ", E, re.M)) != len(re.findall(r"^## ", Z, re.M)):
        bad(f"{rel(en)}: ## sections differ from the mirror")
    if len(re.findall(r"^\| P\d", E, re.M)) != len(re.findall(r"^\| P\d", Z, re.M)):
        bad(f"{rel(en)}: requirement rows differ from the mirror")
for path in sorted(docs):
    text = open(path, encoding="utf-8").read()
    for m in re.finditer(r"\]\(([^)\s]+)\)", text):
        link = m.group(1)
        if link.startswith(("http://", "https://", "mailto:")):
            continue
        target, _, anchor = link.partition("#")
        tp = os.path.normpath(os.path.join(os.path.dirname(path), target)) if target else path
        if not os.path.exists(tp):
            bad(f"{rel(path)}: broken link {link}")
        elif anchor and tp.endswith(".md"):
            heads = {slug(h) for h in re.findall(r"^#{1,6} (.+)$", open(tp, encoding="utf-8").read(), re.M)}
            if anchor not in heads:
                bad(f"{rel(path)}: missing anchor {link}")

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)
print(f"valid: {len(schemas)} schemas, {len(be['reasons'])} be reasons, {len(cat_keys)} config keys, "
      f"{len(cases['cases'])} cases, {len(vector_files)} vector files, {n_headers} envelope header sets, {len(docs)} documents")
