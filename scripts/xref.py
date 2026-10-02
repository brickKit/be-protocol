#!/usr/bin/env python3
"""Cross-references of requirement and case IDs (make xref).

- Requirements are the rows `| P<n>.<m> |` of spec/NN-*.md; the English and Chinese files define
  the same set.
- Every P<n>.<m> cited anywhere in this repository (spec, README, schemas, ddl, proto, openapi,
  vectors, fixtures) is defined.
- Every CP-<GROUP>-<nn> cited in spec/ or README is in schemas/conformance-cases.yaml, every
  catalogue case tests defined requirements, and every catalogue case is cited by spec/.
- Optional: `xref.py <file or dir> …` also checks the requirement and case IDs cited in other
  documents (for example an assembly project's foundations), read-only.
Standard library and PyYAML only. Exit 1 on any finding.
"""
import collections
import glob
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQ = re.compile(r"(?<![A-Za-z0-9.])P(\d{1,2})\.(\d{1,2})(?![0-9])")
CASE = re.compile(r"CP-[A-Z]+-\d{2}")
findings = []


def defined(lang):
    ids = set()
    for f in glob.glob(os.path.join(ROOT, "spec", "[0-9][0-9]-*.md")):
        if f.endswith(".zh.md") != (lang == "zh"):
            continue
        ids |= set(re.findall(r"^\| (P\d+\.\d+) \|", open(f, encoding="utf-8").read(), re.M))
    return ids


def files_under(paths):
    for p in paths:
        if os.path.isdir(p):
            for f in glob.glob(os.path.join(p, "**", "*"), recursive=True):
                if os.path.isfile(f) and "/.git/" not in f:
                    yield f
        elif os.path.isfile(p):
            yield p


def cited(paths, pattern=REQ, chapters=True):
    out = collections.defaultdict(set)
    for f in files_under(paths):
        try:
            text = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for m in pattern.finditer(text):
            if chapters:
                c = int(m.group(1))
                if not 1 <= c <= 20:
                    continue
                key = f"P{c}.{int(m.group(2))}"
            else:
                key = m.group(0)
            out[key].add(os.path.relpath(f, ROOT))
    return out


en, zh = defined("en"), defined("zh")
if en != zh:
    findings.append(f"requirements differ between English and Chinese: {sorted(en ^ zh)}")
own = [os.path.join(ROOT, d) for d in ("spec", "schemas", "ddl", "proto", "openapi", "vectors", "fixtures", "scripts/examples")] + \
      [os.path.join(ROOT, f) for f in ("README.md", "README.zh.md", "CHANGELOG.md", "CHANGELOG.zh.md")]
for rid, where in sorted(cited(own).items()):
    if rid not in en:
        findings.append(f"{rid} is cited but not defined: {', '.join(sorted(where))[:200]}")

cat = yaml.safe_load(open(os.path.join(ROOT, "schemas", "conformance-cases.yaml"), encoding="utf-8"))
cases = {c["id"] for c in cat["cases"]}
docs = [os.path.join(ROOT, "spec"), os.path.join(ROOT, "README.md"), os.path.join(ROOT, "README.zh.md"), os.path.join(ROOT, "fixtures")]
for cid, where in sorted(cited(docs, CASE, chapters=False).items()):
    if cid not in cases:
        findings.append(f"{cid} is cited but not in the catalogue: {', '.join(sorted(where))[:200]}")
for c in cat["cases"]:
    for t in c["tests"]:
        if t not in en:
            findings.append(f"{c['id']} tests an undefined requirement {t}")
spec_cases = set()
for f in glob.glob(os.path.join(ROOT, "spec", "[0-9][0-9]-*.md")):
    if not f.endswith(".zh.md"):
        spec_cases |= set(CASE.findall(open(f, encoding="utf-8").read()))
for cid in sorted(cases - spec_cases):
    findings.append(f"{cid} is in the catalogue but cited by no requirement")

extra = sys.argv[1:]
if extra:
    for rid, where in sorted(cited(extra).items()):
        if rid not in en:
            findings.append(f"[extra] {rid} is cited but not defined: {', '.join(sorted(where))[:200]}")
    for cid, where in sorted(cited(extra, CASE, chapters=False).items()):
        if cid not in cases:
            findings.append(f"[extra] {cid} is cited but not in the catalogue: {', '.join(sorted(where))[:200]}")

for f in findings:
    print("FAIL", f)
print(f"xref: {len(en)} requirements, {len(cases)} cases, {len(findings)} finding(s)")
sys.exit(1 if findings else 0)
