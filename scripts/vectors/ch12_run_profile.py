"""Chapter 12: the run profile's deterministic parts (P12.1-P12.4). Signing and verifying are the SDKs' own tests:
the generator has no cryptography (python3 -I), and ECDSA signatures are not reproducible byte for byte."""
from ch08_canonical import canonical
from common import write

RETENTION_DAYS = {"generation.deployment": 3650, "generation.authz": 3650, "trust.ca": 3650, "trust.credential": 3650,
                  "alert": 30, "recovery.step": 30}
DEP = "0190f3a1-0000-7000-8000-00000000d001"


def key(deployment, kind, written_at, rid):
    """<deployment>/<kind>/<YYYY>/<MM>/<DD>/<written_at>-<id>.json (P12.1)."""
    return f"{deployment}/{kind}/{written_at[0:4]}/{written_at[5:7]}/{written_at[8:10]}/{written_at}-{rid}.json"


def record(kind, rid, written_at, body):
    return {"record_type": "be.ops.run_profile_record", "schema": "1.0", "deployment": DEP, "kind": kind, "id": rid,
            "written_at": written_at, "writer": {"component": "infra/authz", "instance": "authz-1"}, "body": body}


def current(records):
    """A generation's current value: the largest body.value among the records whose signature holds; 0 when none."""
    vals = [r["body"]["value"] for r in records if r["signature_holds"]]
    return max(vals) if vals else 0


def run_profile_vectors():
    cases = []
    r = record("generation.authz", "0190f3a1-0000-7000-8000-0000000000e1", "2026-11-05T10:15:30.123456Z", {"value": 3})
    cases.append({"id": "signed-bytes", "input": {"record": r},
                  "expected": {"signed_bytes": canonical(r).decode(),
                               "key": key(DEP, "generation.authz", r["written_at"], r["id"])}})
    cases.append({"id": "signature-excluded",
                  "description": "the signature member is not part of the signed bytes: the same bytes with it present",
                  "input": {"record": {**r, "signature": {"alg": "ES256", "value": "AAAA", "cert_chain": "-----BEGIN"}}},
                  "expected": {"signed_bytes": canonical(r).decode()}})
    for kind, days in sorted(RETENTION_DAYS.items()):
        cases.append({"id": f"retention-{kind}", "input": {"kind": kind}, "expected": {"min_retention_days": days}})
    gens = [
        ("none", [], 0),
        ("max-of-valid", [{"body": {"value": 2}, "signature_holds": True}, {"body": {"value": 5}, "signature_holds": True},
                          {"body": {"value": 4}, "signature_holds": True}], 5),
        ("invalid-ignored", [{"body": {"value": 2}, "signature_holds": True},
                             {"body": {"value": 9}, "signature_holds": False}], 2),
    ]
    for name, recs, want in gens:
        cases.append({"id": f"generation-{name}", "input": {"records": recs}, "expected": {"current": want}})
        assert current(recs) == want
    advance = [("everywhere-equal", {"run_profile": 4, "evidence": 4, "databases": [4, 4]}, 5),
               ("evidence-restored-from-backup", {"run_profile": 6, "evidence": 3, "databases": [3, 5]}, 7),
               ("a-database-ahead", {"run_profile": 2, "evidence": 2, "databases": [2, 8]}, 9)]
    for name, seen, want in advance:
        cases.append({"id": f"advance-{name}", "description": "P12.5: the largest value seen anywhere, plus one",
                      "input": seen, "expected": {"next": want}})
        assert max([seen["run_profile"], seen["evidence"], *seen["databases"]]) + 1 == want
    write("run-profile", ["P12.1", "P12.2", "P12.3", "P12.4", "P12.5"],
          "运行档案：签名前的规范字节（去掉 signature 成员）、键名、各类别的最短保留期、恢复代次的当前值（签名成立的最大值）与推进（各处最大值加一）",
          cases, {"input": "record | kind | records | seen", "expected": "signed_bytes, key | min_retention_days | current | next"})
