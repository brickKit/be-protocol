package protocol

// Chapter 17: independent recomputation of the flow-kernel vectors.

import (
	"encoding/json"
	"testing"
)

type flowCase struct {
	Task, Instance           string
	Version, Self, Candidate bool
	Operation                bool
	Qualification            string
	Revision, Replay         bool
	Decision, Form           string
	Others, LastStep         bool   `json:"-"`
	RejectOutcome            string `json:"reject_outcome"`
}

type flowOutcome struct {
	Answer   string `json:"answer"`
	Task     string `json:"task"`
	Instance string `json:"instance"`
	Others   string `json:"others"`
	NextStep bool   `json:"next_step"`
	Changed  bool   `json:"changed"`
}

// flowRecompute reads P17.10's checks as a table of refusals, then P17.13's outcome as a table of ends (the generator
// writes one chain of ifs), so a slip in either shows up.
func flowRecompute(c flowCase, others, last bool) flowOutcome {
	keep := flowOutcome{Task: c.Task, Instance: c.Instance, Others: "unchanged"}
	if c.Replay { // P17.11
		keep.Answer = "replay"
		return keep
	}
	qual := map[string]string{"qualified": "", "not_qualified": "NOT_QUALIFIED", "unknown": "QUALIFICATION_UNKNOWN"}[c.Qualification]
	for _, r := range []struct {
		fails  bool
		reason string
	}{
		{c.Task != "pending" || c.Instance != "running", "TASK_NOT_PENDING"},
		{!c.Version, "VERSION_CONFLICT"},
		{c.Self, "SELF_APPROVAL"},
		{!c.Candidate, "NOT_ASSIGNEE"},
		{!c.Operation, "PERMISSION_DENIED"},
		{qual != "", qual},
		{!c.Revision, "REVISION_CHANGED"},
	} {
		if r.fails {
			keep.Answer = r.reason
			return keep
		}
	}
	out := flowOutcome{Answer: "ok", Task: "decided", Instance: "running", Others: "unchanged", Changed: true}
	if others {
		out.Others = "superseded"
	}
	switch {
	case c.Decision == "reject":
		out.Instance = c.RejectOutcome
	case last:
		out.Instance = "approved"
	default:
		out.NextStep = true
	}
	return out
}

func TestFlowKernelVectors(t *testing.T) {
	seen := map[string]bool{}
	for _, raw := range load(t, "flow-kernel").Cases {
		var v struct {
			ID   string
			Case struct {
				flowCase
				Others   bool `json:"others"`
				LastStep bool `json:"last_step"`
			}
			Expect flowOutcome
		}
		if err := json.Unmarshal(raw, &v); err != nil {
			t.Fatal(err)
		}
		if got := flowRecompute(v.Case.flowCase, v.Case.Others, v.Case.LastStep); got != v.Expect {
			t.Errorf("%s: recomputed %+v, vector %+v", v.ID, got, v.Expect)
		}
		seen[v.Expect.Answer] = true
	}
	// every refusal of P17.10, the replay of P17.11 and an outcome are met
	for _, a := range []string{"ok", "replay", "TASK_NOT_PENDING", "VERSION_CONFLICT", "SELF_APPROVAL", "NOT_ASSIGNEE",
		"PERMISSION_DENIED", "NOT_QUALIFIED", "QUALIFICATION_UNKNOWN", "REVISION_CHANGED"} {
		if !seen[a] {
			t.Errorf("no vector answers %s", a)
		}
	}
}
