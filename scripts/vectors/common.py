"""Shared parts of the vector generators: where vectors go and how one file is written."""
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROTOCOL = "3.0.0-alpha.16"
VEC = ROOT / "vectors"


def write(topic, rules, description, cases, fields):
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), f"{topic}: duplicate ids"
    doc = {"topic": topic, "protocol": PROTOCOL, "rules": rules, "description": description,
           "fields": fields, "cases": cases}
    (VEC / f"{topic}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


def sums():
    lines = []
    for p in sorted(VEC.glob("*.json")):
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (VEC / "SHA256SUMS").write_text("\n".join(lines) + "\n")
