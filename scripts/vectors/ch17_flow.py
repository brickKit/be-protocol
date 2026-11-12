"""Chapter 17: a flow kernel's decision (P17.2, P17.6, P17.10, P17.11, P17.13)."""
from common import write

GOOD = {"task": "pending", "instance": "running", "version": True, "self": False, "candidate": True,
        "operation": True, "qualification": "qualified", "revision": True, "replay": False}
CHECKS = [  # in the order P17.10 checks them: the first that fails answers
    ("task", lambda c: c["task"] == "pending" and c["instance"] == "running", "TASK_NOT_PENDING"),
    ("version", lambda c: c["version"], "VERSION_CONFLICT"),
    ("self", lambda c: not c["self"], "SELF_APPROVAL"),
    ("candidate", lambda c: c["candidate"], "NOT_ASSIGNEE"),
    ("operation", lambda c: c["operation"], "PERMISSION_DENIED"),
    ("qualification", lambda c: c["qualification"] == "qualified", None),
    ("revision", lambda c: c["revision"], "REVISION_CHANGED"),
]


def decide(c):
    """The reference: the answer, the task after, the instance after, the other pending tasks of the step, whether the
    next step's tasks are made, whether anything changed (versions up, projections published)."""
    keep = {"answer": None, "task": c["task"], "instance": c["instance"], "others": "unchanged", "next_step": False,
            "changed": False}
    if c["replay"]:  # P17.11: the same key answers the first result, before any check
        return {**keep, "answer": "replay"}
    for name, ok, reason in CHECKS:
        if not ok(c):
            if name == "qualification":
                reason = "QUALIFICATION_UNKNOWN" if c["qualification"] == "unknown" else "NOT_QUALIFIED"
            return {**keep, "answer": reason}
    out = {"answer": "ok", "task": "decided", "instance": "running", "others": "unchanged", "next_step": False,
           "changed": True}
    if c["others"]:  # P17.2: any; P17.6: an ending instance supersedes the rest
        out["others"] = "superseded"
    if c["decision"] == "reject":  # P17.13: the definition's outcome
        out["instance"] = c["reject_outcome"]
    elif c["last_step"]:
        out["instance"] = "approved"
    else:
        out["next_step"] = True
    return out


def flow_vectors():
    cases = []

    def add(cid, **change):
        c = {**GOOD, "decision": "approve", "form": "single", "others": False, "last_step": True,
             "reject_outcome": "rejected", **change}
        cases.append({"id": cid, "case": c, "expect": decide(c)})

    # each check failing alone, and together with the later ones (the first wins)
    add("task-decided", task="decided")
    add("task-superseded", task="superseded")
    add("task-paused", task="paused")
    add("instance-approved", instance="approved")
    add("instance-superseded", instance="superseded")
    add("version-stale", version=False)
    add("self", self=True)
    add("self-and-not-candidate", self=True, candidate=False)
    add("not-candidate", candidate=False)
    add("no-operation", operation=False)
    add("not-qualified", qualification="not_qualified")
    add("qualification-unknown", qualification="unknown")
    add("revision-changed", revision=False)
    add("stale-and-self", version=False, self=True)
    add("decided-and-everything-wrong", task="decided", version=False, self=True, candidate=False, operation=False,
        qualification="unknown", revision=False)
    # replays answer before any check
    add("replay", replay=True)
    add("replay-of-a-decided-task", replay=True, task="decided", version=False)
    # outcomes
    add("approve-last-single")
    add("approve-not-last", last_step=False)
    add("approve-any-others", form="any", others=True)
    add("approve-any-others-not-last", form="any", others=True, last_step=False)
    add("reject-rejected", decision="reject")
    add("reject-returned", decision="reject", reject_outcome="returned")
    add("reject-not-last", decision="reject", last_step=False)
    add("reject-any-others", decision="reject", form="any", others=True, reject_outcome="returned")
    write("flow-kernel", ["P17.2", "P17.6", "P17.10", "P17.11", "P17.13"],
          "流程内核的一次决定：case 是到达时的情形——task 与 instance 是任务与实例现在的状态，version 是任务版本是否相同，self "
          "是决定者这个人是不是发起人这个人，candidate 是不是候选处理人，operation 是否有流程定义要的操作，qualification 是此刻"
          "按分配规则是否合格（qualified、not_qualified、unknown：投影不完整），revision 是实例的关键修订号是否等于单据现在的，"
          "replay 是同一个幂等键是否已有结果；decision 是 approve 或 reject，form 是步骤的形式（single、any），others 是这一步还有"
          "别的待处理任务，last_step 是不是最后一步，reject_outcome 是流程定义的拒绝结果（rejected、returned）。expect：answer 是 "
          "ok、replay（照答第一次的结果）或第一个不满足的检查的原因（按 P17.10 的顺序）；task、instance 是之后的状态；others 是这一步"
          "其余待处理任务之后的样子（superseded 或 unchanged）；next_step 是否为下一步建任务；changed 是否有改变（版本加一、发任务投影）。",
          cases, {"case": "到达时的情形", "expect": "结果"})
