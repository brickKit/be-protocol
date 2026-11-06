"""Chapter 12: evidence records (P12.9, P12.10): the categories, the canonical digest, and how the store answers a
record by (id, phase)."""
from ch08_canonical import digest
from common import write

CATEGORIES = ["security_tightening", "security_widening", "employment_end", "org_tightening", "account_status",
              "account_reenable", "identity_signing_key_revocation", "credential_tightening",
              "credential_tightening_in_product", "session_revocation", "recovery_credential_rotation",
              "document_number", "member_switch_handover", "destruction", "external_command_issued",
              "external_command_outcome", "trust_material", "deployment_generation", "authz_generation",
              "evidence_double_failure"]
REC = {"component": "infra/authz", "instance": "authz-1"}


def ev(phase, **kw):
    r = {"record_type": "be.evidence.record", "schema": "1.0", "id": "0190f3a1-0000-7000-8000-0000000000e7",
         "recorder": REC, "category": "security_tightening", "phase": phase,
         "subject": "0190f3a1-0000-7000-8000-0000000000b2",
         "object": {"type": "infra.authz.security_record", "id": "0190f3a1-0000-7000-8000-0000000000f1", "version": "3"},
         "change": {"termination": "revoke"}, "at": "2026-11-05T10:20:00.000000Z"}
    if phase in ("effective", "general"):  # committed with the business transaction (P12.9)
        r["position"] = {"epoch": "1.1", "commit_seq": 107}
    r.update(kw)
    return r


def answer(stored, incoming):
    """What the store answers (P12.10): stored is the list already kept."""
    for s in stored:
        if s["id"] == incoming["id"] and s["phase"] == incoming["phase"]:
            return "duplicate" if digest("be.evidence.record", 1, s) == digest("be.evidence.record", 1, incoming) else "conflict"
    if incoming["phase"] in ("effective", "cancelled"):
        for s in stored:
            if s["id"] == incoming["id"] and s["phase"] == "intent":
                same = all(s[k] == incoming[k] for k in ("recorder", "category", "subject", "object"))
                return "accepted" if same else "conflict"
    return "accepted"


def evidence_vectors():
    cases = [{"id": "categories", "expected": {"categories": CATEGORIES}},
             {"id": "position-by-phase", "description": "only effective and general carry a position",
              "expected": {"with_position": ["effective", "general"], "without_position": ["intent", "cancelled"]}}]
    for phase in ("intent", "effective", "cancelled", "general"):
        r = ev(phase)
        cases.append({"id": f"digest-{phase}", "input": {"record": r},
                      "expected": {"digest": digest("be.evidence.record", 1, r)}})
    intent, eff = ev("intent"), ev("effective")
    flows = [
        ("first-intent", [], intent),
        ("same-intent-again", [intent], intent),
        ("intent-other-bytes", [intent], ev("intent", change={"termination": "narrow"})),
        ("conclusion-matches", [intent], eff),
        ("conclusion-other-subject", [intent], ev("effective", subject="0190f3a1-0000-7000-8000-0000000000c3")),
        ("conclusion-without-intent", [], eff),
        ("cancelled-after-intent", [intent], ev("cancelled")),
        ("conclusion-again-other-position", [intent, eff], ev("effective", position={"epoch": "1.1", "commit_seq": 108})),
    ]
    for name, stored, incoming in flows:
        cases.append({"id": f"store-{name}", "input": {"stored": stored, "incoming": incoming},
                      "expected": {"answer": answer(stored, incoming)}})
    want = {"first-intent": "accepted", "same-intent-again": "duplicate", "intent-other-bytes": "conflict",
            "conclusion-matches": "accepted", "conclusion-other-subject": "conflict",
            "conclusion-without-intent": "accepted", "cancelled-after-intent": "accepted",
            "conclusion-again-other-position": "conflict"}
    for c in cases:
        if c["id"].startswith("store-"):
            assert c["expected"]["answer"] == want[c["id"][6:]], c["id"]
    write("evidence-record", ["P12.9", "P12.10"],
          "证据记录：类别的取值、规范摘要（前缀 be.evidence.record.v1），证据存储按（id，phase）的回答：已收下、重复、冲突",
          cases, {"input": "record | stored, incoming", "expected": "categories | digest | answer"})
