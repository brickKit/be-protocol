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


# P12.24-P12.26: the trust material's history. A CA is trusted when the configured trust root is it, or when a rotation
# from it to a trusted CA holds both signatures (the previous CA's and the next one's acceptance). A signed record
# received at t holds when its chain ends at a trusted CA and no certificate of the chain was revoked at r with
# t > r - skew (a revocation counts only when its own signer was trusted when it was received).
SKEW = 2


def trusted_cas(configured, rotations):
    trusted = set(configured)
    changed = True
    while changed:
        changed = False
        for r in rotations:
            if r["next"] in trusted and r["signed_by_previous"] and r["accepted_by_next"] and r["previous"] not in trusted:
                trusted.add(r["previous"])
                changed = True
    return trusted


def judge(record, configured, rotations, revocations):
    trusted = trusted_cas(configured, rotations)
    if record["chain"][-1] not in trusted:
        return {"holds": False, "reason": "untrusted_ca"}
    for fp in record["chain"]:
        for rv in revocations:
            if rv["fingerprint"] == fp and rv["signer_trusted"] and record["received"] > rv["received"] - SKEW:
                return {"holds": False, "reason": "revoked"}
    if "writer" in record and record["writer"] != record["signer"]:  # P12.4: the writer is the signer's identity
        return {"holds": False, "reason": "writer_not_signer"}
    return {"holds": True}


def trust_history_vectors():
    A, B, F, L1, L2 = "ca-a", "ca-b", "ca-fake", "leaf-1", "leaf-2"
    good = {"previous": A, "next": B, "signed_by_previous": True, "accepted_by_next": True}
    cases = []

    def case(cid, description, record, configured, rotations, revocations, want):
        got = judge(record, configured, rotations, revocations)
        assert got == want, (cid, got, want)
        cases.append({"id": cid, "description": description,
                      "input": {"record": record, "configured": configured, "rotations": rotations,
                                "revocations": revocations, "skew": SKEW},
                      "expected": want})

    case("one-ca", "the configured CA, nothing revoked", {"chain": [L1, A], "received": 50}, [A], [], [], {"holds": True})
    case("rotated-old-ca", "rotated A to B with both signatures: a record under A still holds",
         {"chain": [L1, A], "received": 50}, [B], [good], [], {"holds": True})
    case("rotation-without-acceptance", "the next CA did not accept: A is not trusted",
         {"chain": [L1, A], "received": 50}, [B], [{**good, "accepted_by_next": False}], [],
         {"holds": False, "reason": "untrusted_ca"})
    case("forged-rotation", "a rotation from a fake CA to the trusted one, signed by the fake only",
         {"chain": [L2, F], "received": 50}, [B], [{"previous": F, "next": B, "signed_by_previous": True,
                                                     "accepted_by_next": False}], [],
         {"holds": False, "reason": "untrusted_ca"})
    case("not-on-the-chain", "a CA no rotation links to the configured root",
         {"chain": [L2, F], "received": 50}, [A], [], [], {"holds": False, "reason": "untrusted_ca"})
    rv = [{"fingerprint": L1, "received": 100, "signer_trusted": True}]
    case("before-the-revocation", "received well before the revocation", {"chain": [L1, A], "received": 97}, [A], [], rv,
         {"holds": True})
    case("within-the-skew", "received less than the declared skew before the revocation: not trusted",
         {"chain": [L1, A], "received": 99}, [A], [], rv, {"holds": False, "reason": "revoked"})
    case("after-the-revocation", "received after the revocation", {"chain": [L1, A], "received": 150}, [A], [], rv,
         {"holds": False, "reason": "revoked"})
    case("ca-revoked", "the CA itself revoked: every chain under it after that",
         {"chain": [L1, A], "received": 150}, [B], [good], [{"fingerprint": A, "received": 120, "signer_trusted": True}],
         {"holds": False, "reason": "revoked"})
    case("revocation-by-an-untrusted-signer", "a revocation whose own signer is not trusted does not count",
         {"chain": [L1, A], "received": 150}, [A], [], [{"fingerprint": L1, "received": 100, "signer_trusted": False}],
         {"holds": True})
    case("writer-is-signer", "a service credential's record names its own component as the writer",
         {"chain": [L1, A], "received": 50, "writer": "infra/authz", "signer": "infra/authz"}, [A], [], [],
         {"holds": True})
    case("writer-not-signer", "another component's credential (unrevoked) signs a record naming the authorization member",
         {"chain": [L2, A], "received": 50, "writer": "infra/authz", "signer": "infra/audit"}, [A], [], [],
         {"holds": False, "reason": "writer_not_signer"})
    write("trust-history", ["P12.4", "P12.24", "P12.25", "P12.26"],
          "信任材料历史：受信的 CA（从配置的信任根沿双签的轮换往前）、一条记录在接收时刻是否可信（链到受信的 CA，链上没有在 t > r − 偏差时已吊销的证书，写入者就是签名证书的服务身份）",
          cases, {"input": "record (chain, received; writer and signer: the component the record names and the one its certificate carries), configured, rotations, revocations, skew", "expected": "holds, reason"})
