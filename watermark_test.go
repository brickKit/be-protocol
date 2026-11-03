package protocol

// Chapter 09: independent recomputation of the watermark source's vectors (P9.15, P9.20, P9.22-P9.24, P9.26, P9.28).

import (
	"encoding/json"
	"reflect"
	"strconv"
	"strings"
	"testing"
)

type epochPair [2]int64

func parseEpochPair(t *testing.T, s string) epochPair {
	g, tl, ok := strings.Cut(s, ".")
	a, err1 := strconv.ParseInt(g, 10, 64)
	b, err2 := strconv.ParseInt(tl, 10, 64)
	if !ok || err1 != nil || err2 != nil {
		t.Fatalf("epoch %q", s)
	}
	return epochPair{a, b}
}

func (e epochPair) cmp(o epochPair) int {
	for i := range e {
		if e[i] != o[i] {
			if e[i] < o[i] {
				return -1
			}
			return 1
		}
	}
	return 0
}

func TestWatermarkPullCheckVectors(t *testing.T) {
	for _, raw := range load(t, "watermark-pull-check").Cases {
		var c struct {
			ID     string
			Source struct {
				Impl, Epoch string
				Counter     uint64
				Rows        map[string]json.RawMessage
			}
			Request struct {
				Position *struct {
					Impl, Epoch string
					Seq         uint64
				}
				Row json.RawMessage
			}
			Expect string
		}
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		// the checks in the order the rule reads them, written as a table of conditions
		got := "ok"
		p := c.Request.Position
		row, kept := json.RawMessage(nil), false
		if p != nil {
			row, kept = c.Source.Rows[strconv.FormatUint(p.Seq, 10)]
		}
		switch {
		case p == nil, p.Impl != c.Source.Impl, p.Epoch != c.Source.Epoch:
			got = "echo_only"
		case p.Seq > c.Source.Counter:
			got = "rollback_detected"
		case !kept:
			got = "beyond_retention"
		case !jsonEqual(t, row, c.Request.Row):
			got = "rollback_detected"
		}
		if got != c.Expect {
			t.Errorf("%s: %s, vector says %s", c.ID, got, c.Expect)
		}
	}
}

func jsonEqual(t *testing.T, a, b json.RawMessage) bool {
	var x, y any
	if json.Unmarshal(a, &x) != nil || json.Unmarshal(b, &y) != nil {
		t.Fatalf("row identities %s, %s", a, b)
	}
	return reflect.DeepEqual(x, y)
}

func TestWatermarkPullOutcomeVectors(t *testing.T) {
	for _, raw := range load(t, "watermark-pull-outcome").Cases {
		var c struct {
			ID       string
			Consumer struct{ Requested *uint64 }
			Response struct {
				Unreachable  bool
				NeedSnapshot string `json:"need_snapshot"`
				EchoSeq      uint64 `json:"echo_seq"`
			}
			Expect string
		}
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		r := c.Response
		got := map[string]string{"": "apply_to_echo", "beyond_retention": "realign", "rollback_detected": "stall"}[r.NeedSnapshot]
		if r.Unreachable {
			got = "hold"
		} else if r.NeedSnapshot == "" && c.Consumer.Requested != nil && r.EchoSeq < *c.Consumer.Requested {
			got = "stall" // the counter went back below what this request carried: P9.29's tripwire
		}
		if got != c.Expect {
			t.Errorf("%s: %s, vector says %s", c.ID, got, c.Expect)
		}
	}
}

func TestWatermarkEpochVectors(t *testing.T) {
	type identity struct {
		Deployment string
		Impl       *string
		SystemID   string `json:"system_id"`
		Epoch      string
		Primary    bool
		Purpose    string
	}
	for _, raw := range load(t, "watermark-epoch").Cases {
		var c struct {
			ID                string
			Adopted, Response identity
			Expect            string
		}
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		a, r := c.Adopted, c.Response
		if r.Deployment == a.Deployment && a.Impl == nil { // the first contact
			got := map[bool]string{true: "establish", false: "discard"}[r.Primary]
			if got != c.Expect {
				t.Errorf("%s: %s, vector says %s", c.ID, got, c.Expect)
			}
			continue
		}
		ae, re := epochPair{}, parseEpochPair(t, r.Epoch)
		if a.Epoch != "" {
			ae = parseEpochPair(t, a.Epoch)
		}
		var got string
		switch {
		case r.Deployment != a.Deployment || a.Impl == nil || *r.Impl != *a.Impl:
			got = "block"
		case !r.Primary:
			got = "discard"
			if r.SystemID == a.SystemID && re == ae && r.Purpose != "adopt" && r.Purpose != "align" {
				got = "use"
			}
		case r.SystemID != a.SystemID && re[0] <= ae[0]:
			got = "stall" // a new system without a larger recovery generation: restored without advancing it
		default:
			got = map[int]string{-1: "ignore", 0: "use", 1: "adopt"}[re.cmp(ae)]
		}
		if got != c.Expect {
			t.Errorf("%s: %s, vector says %s", c.ID, got, c.Expect)
		}
	}
}

func TestWatermarkValueVectors(t *testing.T) {
	for _, raw := range load(t, "watermark-value").Cases {
		var c struct {
			ID    string
			State struct {
				Now           float64
				MaxSeen       float64 `json:"max_seen"`
				ConsumerEpoch string  `json:"consumer_epoch"`
				RecordedEpoch string  `json:"recorded_epoch"`
				Partitions    []struct {
					Contiguous uint64
					Echoes     []struct {
						Seq      uint64
						MP       float64 `json:"m_p"`
						Recorded bool
					}
				}
			}
			Expect *float64
		}
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		s := c.State
		var got *float64
		if s.Now >= s.MaxSeen && s.ConsumerEpoch == s.RecordedEpoch {
			low, every := 0.0, len(s.Partitions) > 0
			for i, p := range s.Partitions {
				last, found := 0.0, false
				for _, e := range p.Echoes {
					if e.Recorded && e.Seq <= p.Contiguous && (!found || e.MP > last) {
						last, found = e.MP, true
					}
				}
				if !found {
					every = false
					break
				}
				if i == 0 || last < low {
					low = last
				}
			}
			if every {
				got = &low
			}
		}
		if (got == nil) != (c.Expect == nil) || (got != nil && *got != *c.Expect) {
			t.Errorf("%s: %v, vector says %v", c.ID, got, c.Expect)
		}
	}
}

func TestWatermarkJudgeVectors(t *testing.T) {
	for _, raw := range load(t, "watermark-judge").Cases {
		var c struct {
			ID    string
			Query struct {
				WatermarkSource bool   `json:"watermark_source"`
				SourceState     string `json:"source_state"`
				ProjectionState string `json:"projection_state"`
				Quarantined     bool
				Watermark       *float64
				Now, Freshness  float64
				Row             *struct {
					State   string
					Adopted bool
				}
			}
			Expect string
		}
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		q := c.Query
		fresh := q.Watermark != nil && *q.Watermark >= q.Now-q.Freshness
		trusted := q.SourceState == "aligned" && q.ProjectionState == "serving" && !q.Quarantined && fresh
		got := "unprovable"
		switch {
		case !q.WatermarkSource:
			got = "query_the_source"
		case !trusted:
		case q.Row == nil:
			got = "provably_absent"
		case !q.Row.Adopted:
		case q.Row.State == "complete":
			got = "usable"
		case q.Row.State == "tombstone":
			got = "provably_absent"
		}
		if got != c.Expect {
			t.Errorf("%s: %s, vector says %s", c.ID, got, c.Expect)
		}
	}
}

func TestWatermarkSourceStateVectors(t *testing.T) {
	type fields struct {
		State      string
		Confirmed  bool
		Rollback   bool
		StalledGen *int64 `json:"stalled_gen"`
		BlockedGen *int64 `json:"blocked_gen"`
		Prior      *string
		Action     string
	}
	for _, raw := range load(t, "watermark-source-state").Cases {
		var c struct {
			ID      string
			Current fields
			Event   struct {
				Kind     string
				Gen      int64
				Matches  bool
				RowCheck string `json:"row_check"`
			}
			Expect fields
		}
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		cur, ev := c.Current, c.Event
		next := cur
		gen := ev.Gen
		above := func(p *int64) bool { return p == nil || gen > *p }
		set := func(state, action string) { next.State, next.Action = state, action }
		// the table's rows in order, first match wins (protocol 02's alignment state table without step 12)
		switch {
		case ev.Kind == "environment_copy":
			set("aligning", "clear_and_refetch")
			next.Rollback, next.Confirmed = false, false
		case ev.Kind == "foreign" && cur.State == "blocked":
			set("blocked", "alert")
		case ev.Kind == "foreign":
			prior := cur.State
			set("blocked", "alert_and_hold")
			next.Prior, next.BlockedGen = &prior, &gen
		case cur.State == "blocked" && ev.Kind == "operator_confirms":
			set("blocked", "record_confirmation")
			next.Confirmed = true
		case cur.State == "blocked" && cur.Confirmed && ev.Kind == "primary_response" && !ev.Matches:
			set("blocked", "alert")
			next.Confirmed = false
		case cur.State == "blocked" && cur.Confirmed && ev.Kind == "primary_response" &&
			cur.Prior != nil && *cur.Prior == "stalled" && !above(cur.StalledGen):
			set("stalled", "refetch")
			next.Confirmed = false
		case cur.State == "blocked" && cur.Confirmed && ev.Kind == "primary_response" && ev.RowCheck == "failed":
			set("stalled", "refetch")
			next.Confirmed, next.Rollback, next.StalledGen = false, true, &gen
		case cur.State == "blocked" && cur.Confirmed && ev.Kind == "primary_response":
			set("aligning", "row_check_then_refetch")
			next.Confirmed = false
		case cur.State == "blocked":
			set("blocked", "hold")
		case ev.Kind == "rollback":
			set("stalled", "refetch")
			next.Rollback, next.StalledGen = true, &gen
		case cur.State == "stalled" && ev.Kind == "adopt_epoch" && above(cur.StalledGen):
			set("aligning", "refetch")
		case cur.State == "stalled":
			set("stalled", "keep_refetching")
		case ev.Kind == "adopt_epoch" || ev.Kind == "first_contact" || ev.Kind == "beyond_retention":
			set("aligning", "refetch")
		case cur.State == "aligning" && ev.Kind == "alignment_done" && cur.Rollback && !above(cur.StalledGen):
			set("stalled", "alert")
		case cur.State == "aligning" && ev.Kind == "alignment_done":
			set("aligned", "watermark_from_echoes")
			next.Rollback = false
		default:
			set(cur.State, "alert")
		}
		if !reflect.DeepEqual(next, c.Expect) {
			t.Errorf("%s: %+v, vector says %+v", c.ID, next, c.Expect)
		}
	}
}
