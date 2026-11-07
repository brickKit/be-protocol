package protocol

// Chapter 16: independent recomputation of the reserve-participant vectors.

import (
	"encoding/json"
	"strings"
	"testing"
)

// reserveOutcome is what a command leaves: the state, the answer, the resource's change and whether the branch changed.
type reserveOutcome struct {
	State    string `json:"state"`
	Answer   string `json:"answer"`
	Resource string `json:"resource"`
	Changed  bool   `json:"changed"`
}

// reserveRecompute reads the chapter's rules from the side of the command, not of the state (the generator goes the
// other way round), so a slip in either shows up.
func reserveRecompute(state string, past bool, cmd string) reserveOutcome {
	stay := reserveOutcome{State: state, Answer: "ok", Resource: "none"}
	if state == "" {
		stay.State = "absent"
	}
	live := state == "held" || state == "committed"
	switch {
	case cmd == "query": // P16.6
		return stay
	case cmd == "hold-enough" && state == "": // P16.3
		return reserveOutcome{"held", "ok", "take", true}
	case cmd == "hold-short" && state == "":
		return reserveOutcome{"rejected", "ok", "none", true}
	case cmd == "hold-other" && state != "cancelled":
		return reserveOutcome{state, "conflict", "none", false}
	case strings.HasPrefix(cmd, "hold"):
		return stay
	case cmd == "confirm" && state == "held" && past: // P16.4
		return reserveOutcome{"expired", "ok", "give_back", true}
	case cmd == "confirm" && state == "held":
		return reserveOutcome{"committed", "ok", "none", true}
	case cmd == "confirm":
		return stay
	case cmd == "cancel" && state == "": // P16.5
		return reserveOutcome{"cancelled", "ok", "none", true}
	case cmd == "cancel" && live:
		return reserveOutcome{"released", "ok", "give_back", true}
	case cmd == "cancel":
		return stay
	case cmd == "expire" && state == "held" && past: // P16.8
		return reserveOutcome{"expired", "ok", "give_back", true}
	case cmd == "expire":
		return stay
	case cmd == "consume-used-same": // P16.7
		return stay
	case cmd == "consume-used-other":
		return reserveOutcome{state, "conflict", "none", false}
	case state == "":
		return reserveOutcome{"absent", "refused:absent", "none", false}
	case state != "committed":
		return reserveOutcome{state, "refused:not_committed", "none", false}
	case cmd == "consume-beyond":
		return reserveOutcome{state, "refused:beyond_remaining", "none", false}
	case cmd == "consume-exact":
		return reserveOutcome{"consumed", "ok", "consume", true}
	case cmd == "consume-within":
		return reserveOutcome{"committed", "ok", "consume", true}
	}
	return reserveOutcome{Answer: "no rule for " + cmd}
}

func TestReserveParticipantVectors(t *testing.T) {
	seen := map[string]bool{}
	for _, raw := range load(t, "reserve-participant").Cases {
		var c struct {
			ID      string
			Current *struct {
				State string
				Past  bool
			}
			Command string
			Expect  reserveOutcome
		}
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		state, past := "", false
		if c.Current != nil {
			state, past = c.Current.State, c.Current.Past
		}
		seen[state+"/"+c.Command] = true
		if got := reserveRecompute(state, past, c.Command); got != c.Expect {
			t.Errorf("%s: recomputed %+v, vector %+v", c.ID, got, c.Expect)
		}
	}
	// every state of P16.1 meets every command that applies to it
	for _, st := range []string{"held", "committed", "consumed", "released", "expired", "rejected", "cancelled"} {
		for _, cmd := range []string{"query", "confirm", "cancel", "expire", "hold-same", "hold-other", "consume-within",
			"consume-exact", "consume-beyond", "consume-used-same", "consume-used-other"} {
			if !seen[st+"/"+cmd] {
				t.Errorf("no vector for %s in %s", cmd, st)
			}
		}
	}
}
