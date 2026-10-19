package protocol

import (
	"encoding/json"
	"maps"
	"strconv"
	"strings"
	"testing"
)

type refRev struct {
	Domain, Epoch, Value, Instance string
}

type refHeldShard struct {
	Revisions []refRev
	Stopped   bool
	Suspended bool
}

// refEpochBefore orders "<generation>.<timeline>" by the two integers.
func refEpochBefore(a, b string) bool {
	ag, at, _ := strings.Cut(a, ".")
	bg, bt, _ := strings.Cut(b, ".")
	x, _ := strconv.Atoi(ag)
	y, _ := strconv.Atoi(bg)
	if x != y {
		return x < y
	}
	u, _ := strconv.Atoi(at)
	v, _ := strconv.Atoi(bt)
	return u < v
}

func refGoesBack(held, next []refRev) bool {
	for _, n := range next {
		for _, h := range held {
			if h.Domain != n.Domain {
				continue
			}
			hv, _ := strconv.Atoi(h.Value)
			nv, _ := strconv.Atoi(n.Value)
			if refEpochBefore(n.Epoch, h.Epoch) || (n.Epoch == h.Epoch && nv < hv) {
				return true
			}
		}
	}
	return false
}

func TestViewAcceptVectors(t *testing.T) {
	for _, raw := range load(t, "view-accept").Cases {
		var c struct {
			ID   string
			Held struct {
				Recovery *int
				Instance *string
				Shards   map[string]refHeldShard
			}
			Answer struct {
				Recovery int
				Instance string
				Shards   []struct {
					Shard, Status string
					View          *struct {
						SecurityRevisions []refRev `json:"security_revisions"`
					}
				}
			}
			Expect struct {
				Answer   string
				Instance *string
				Shards   map[string]string
			}
		}
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		verdict, got := "accepted", map[string]string{}
		foreign := c.Held.Instance != nil && *c.Held.Instance != c.Answer.Instance
		for _, a := range c.Answer.Shards {
			if a.View != nil {
				for _, r := range a.View.SecurityRevisions {
					foreign = foreign || r.Instance != c.Answer.Instance
				}
			}
		}
		older := c.Held.Recovery != nil && c.Answer.Recovery < *c.Held.Recovery
		newer := c.Held.Recovery == nil || c.Answer.Recovery > *c.Held.Recovery
		held := maps.Clone(c.Held.Shards)
		switch {
		case older || foreign:
			verdict = "rollback"
			for k, s := range held {
				got[k] = map[bool]string{true: "stopped", false: "suspended"}[s.Stopped]
			}
		default:
			if newer {
				for k := range held {
					got[k] = "dropped"
				}
				held = nil
			}
			for k, s := range held {
				got[k] = "kept"
				if s.Suspended {
					got[k] = "suspended"
				}
				if s.Stopped {
					got[k] = "stopped"
				}
			}
			for _, a := range c.Answer.Shards {
				s, ok := held[a.Shard]
				switch {
				case a.Status == "unchanged" && ok && !s.Stopped:
					got[a.Shard] = "renewed"
				case a.Status == "changed" && ok && s.Stopped:
				case a.Status == "changed" && ok && refGoesBack(s.Revisions, a.View.SecurityRevisions):
					got[a.Shard] = "stopped"
				case a.Status == "changed":
					got[a.Shard] = "replaced"
				}
			}
		}
		instance := c.Held.Instance
		if verdict == "accepted" {
			instance = &c.Answer.Instance
		}
		if verdict != c.Expect.Answer || !maps.Equal(got, c.Expect.Shards) ||
			(instance == nil) != (c.Expect.Instance == nil) || (instance != nil && *instance != *c.Expect.Instance) {
			t.Errorf("%s: got %s %v, the vector says %s %v", c.ID, verdict, got, c.Expect.Answer, c.Expect.Shards)
		}
	}
}

func TestAuditPurgeVectors(t *testing.T) {
	for _, raw := range load(t, "audit-purge").Cases {
		var c struct {
			ID        string
			Watermark struct {
				Epoch           string
				Seq             int
				Ancestors       map[string]int
				BackedUpInEpoch bool `json:"backed_up_in_epoch"`
			}
			Receipt struct {
				Epoch    string
				Seq      int
				Retained bool
			}
			Expect string
		}
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		w, r := c.Watermark, c.Receipt
		fork, ancestor := w.Ancestors[r.Epoch]
		var got string
		switch {
		case r.Epoch == w.Epoch && r.Seq <= w.Seq && r.Retained:
			got = "delete"
		case r.Epoch == w.Epoch:
			got = "keep"
		case ancestor && r.Seq > fork:
			got = "resend"
		case ancestor && w.BackedUpInEpoch && r.Retained:
			got = "delete"
		case ancestor, refEpochBefore(w.Epoch, r.Epoch):
			got = "keep"
		default:
			got = "resend"
		}
		if got != c.Expect {
			t.Errorf("%s: got %s, the vector says %s", c.ID, got, c.Expect)
		}
	}
}
