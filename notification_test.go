package protocol

// Chapter 18: independent recomputation of the notification-intent vectors, and the intent schema's examples.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/fs"
	"slices"
	"strings"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

type admitCase struct {
	Kind                 string
	SenderIsSource       bool `json:"sender_is_source"`
	ShapeOK              bool `json:"shape_ok"`
	Category             string
	ExpiresAfterOccurred bool `json:"expires_after_occurred"`
	Seen                 bool
	CollapseSeq          *int `json:"collapse_seq"`
	MaxSeq               *int `json:"max_seq"`
}

type admitOutcome struct {
	Answer     string `json:"answer"`
	Supersedes bool   `json:"supersedes"`
	Delivers   bool   `json:"delivers"`
}

var intentCategories = []string{"approval_task", "due_reminder", "security_alert", "legal_notice", "external_comm", "marketing"}

// admitRecompute reads P18.8's refusals as a table (the generator writes a chain of ifs), then P18.9 and P18.7.
func admitRecompute(c admitCase) admitOutcome {
	for _, r := range []struct {
		fails  bool
		reason string
	}{
		{!c.ShapeOK, "malformed"},
		{!c.SenderIsSource, "not_the_sender"},
		{!slices.Contains(intentCategories, c.Category), "unknown_category"},
		{c.Kind == "deliver" && !c.ExpiresAfterOccurred, "malformed"},
		{c.Seen, "duplicate"},
		{c.CollapseSeq != nil && c.MaxSeq != nil && *c.CollapseSeq <= *c.MaxSeq, "stale"},
	} {
		if r.fails {
			return admitOutcome{Answer: r.reason}
		}
	}
	return admitOutcome{Answer: "accepted", Supersedes: c.CollapseSeq != nil, Delivers: c.Kind == "deliver"}
}

// routeRecompute: a mandatory category is always written in-app, expired or not (P18.6); otherwise an expired
// delivery is not, and a preference counts (P18.3).
func routeRecompute(category, preference string, expired bool) string {
	switch {
	case category == "security_alert" || category == "legal_notice": // in-app is their fallback, expired or not
		return "written"
	case expired:
		return "expired"
	case preference == "off", preference == "unset" && category == "marketing":
		return "preference_off"
	}
	return "written"
}

func TestNotificationIntentVectors(t *testing.T) {
	seen := map[string]bool{}
	for _, raw := range load(t, "notification-intent").Cases {
		var v struct {
			ID   string
			Case struct {
				Step string
				admitCase
				Preference string
				Expired    bool
			}
			Expect json.RawMessage
		}
		if err := json.Unmarshal(raw, &v); err != nil {
			t.Fatal(err)
		}
		switch v.Case.Step {
		case "admit":
			var want admitOutcome
			_ = json.Unmarshal(v.Expect, &want)
			if got := admitRecompute(v.Case.admitCase); got != want {
				t.Errorf("%s: recomputed %+v, vector %+v", v.ID, got, want)
			}
			seen[want.Answer] = true
		case "route":
			var want struct{ Result string }
			_ = json.Unmarshal(v.Expect, &want)
			if got := routeRecompute(v.Case.Category, v.Case.Preference, v.Case.Expired); got != want.Result {
				t.Errorf("%s: recomputed %s, vector %s", v.ID, got, want.Result)
			}
			seen[want.Result] = true
		default:
			t.Errorf("%s: step %q", v.ID, v.Case.Step)
		}
	}
	for _, a := range []string{"accepted", "duplicate", "stale", "not_the_sender", "malformed", "unknown_category",
		"written", "preference_off", "expired"} {
		if !seen[a] {
			t.Errorf("no vector answers %s", a)
		}
	}
}

func intentSchema(t *testing.T) *jsonschema.Schema {
	t.Helper()
	const n = "schemas/notification/intent.v1.schema.json"
	raw, err := fs.ReadFile(Schemas, n)
	if err != nil {
		t.Fatal(err)
	}
	doc, err := jsonschema.UnmarshalJSON(bytes.NewReader(raw))
	if err != nil {
		t.Fatal(err)
	}
	c := jsonschema.NewCompiler()
	c.AssertFormat()
	if err := c.AddResource(n, doc); err != nil {
		t.Fatal(err)
	}
	s, err := c.Compile(n)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

// The intent schema (P18.1, P18.4, P18.5, P18.7): a deliver intent and a withdraw intent pass; each way of breaking
// them is refused.
func TestTheIntentSchema(t *testing.T) {
	s := intentSchema(t)
	base := `"intent_id":"0190f3a1-0000-7000-8000-000000000001","sender":"erp/purchase","category":"approval_task","occurred_at":"2026-11-12T10:00:00Z"`
	deliver := `"kind":"deliver","recipients":[{"principal":"u1"},{"position":{"legal_entity_id":"0190f3a1-0000-7000-8000-000000000002","position_id":"0190f3a1-0000-7000-8000-000000000003","date":"2026-11-12"}}],"title":"PO-1","link":"/workflow/tasks/x","expires_at":"2026-11-13T10:00:00Z"`
	withdraw := `"kind":"withdraw","collapse_key":"task:x","collapse_seq":3`
	many := make([]string, 1001)
	for i := range many {
		many[i] = fmt.Sprintf(`{"principal":"u%d"}`, i)
	}
	for _, c := range []struct {
		name, body string
		ok         bool
	}{
		{"deliver", base + "," + deliver, true},
		{"deliver with a merge key and a template", base + "," + deliver + `,"collapse_key":"task:x","collapse_seq":2,"template":"be.flow.task.pending","params":{"number":"PO-1"}`, true},
		{"withdraw", base + "," + withdraw, true},
		{"withdraw with recipients", base + "," + withdraw + `,"recipients":[{"principal":"u1"}]`, false},
		{"withdraw with an expiry", base + "," + withdraw + `,"expires_at":"2026-11-13T10:00:00Z"`, false},
		{"withdraw without a sequence", base + `,"kind":"withdraw","collapse_key":"task:x"`, false},
		{"deliver without a title", base + "," + strings.Replace(deliver, `"title":"PO-1",`, "", 1), false},
		{"deliver with no recipient", base + `,"kind":"deliver","recipients":[],"title":"t","link":"/x","expires_at":"2026-11-13T10:00:00Z"`, false},
		{"1001 recipients", base + `,"kind":"deliver","recipients":[` + strings.Join(many, ",") + `],"title":"t","link":"/x","expires_at":"2026-11-13T10:00:00Z"`, false},
		{"a link outside the system", base + "," + strings.Replace(deliver, `"/workflow/tasks/x"`, `"https://evil.example/x"`, 1), false},
		{"a protocol-relative link", base + "," + strings.Replace(deliver, `"/workflow/tasks/x"`, `"//evil.example/x"`, 1), false},
		{"a backslash link", base + "," + strings.Replace(deliver, `"/workflow/tasks/x"`, `"/\\evil.example/x"`, 1), false},
		{"the root", base + "," + strings.Replace(deliver, `"/workflow/tasks/x"`, `"/"`, 1), true},
		{"an unknown category", strings.Replace(base, "approval_task", "newsletter", 1) + "," + deliver, false},
		{"a merge key without a sequence", base + "," + deliver + `,"collapse_key":"task:x"`, false},
		{"params without a template", base + "," + deliver + `,"params":{"a":"b"}`, false},
		{"an unknown field", base + "," + deliver + `,"priority":"high"`, false},
		{"a title too long", base + "," + strings.Replace(deliver, `"PO-1"`, `"`+strings.Repeat("x", 201)+`"`, 1), false},
	} {
		doc, err := jsonschema.UnmarshalJSON(strings.NewReader("{" + c.body + "}"))
		if err != nil {
			t.Fatalf("%s: %v", c.name, err)
		}
		if err := s.Validate(doc); (err == nil) != c.ok {
			t.Errorf("%s: valid=%v, want %v (%v)", c.name, err == nil, c.ok, err)
		}
	}
}
