package protocol

// Chapter 20: independent recomputation of the channel-action vectors (P20.7, P20.8), and the channel schemas.

import (
	"bytes"
	"encoding/json"
	"io/fs"
	"strings"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

type actionCase struct {
	ShapeOK              bool   `json:"shape_ok"`
	AudienceIsSelf       bool   `json:"audience_is_self"`
	StreamIsSource       bool   `json:"stream_is_source"`
	GrantExists          bool   `json:"grant_exists"`
	PrincipalMatches     bool   `json:"principal_matches"`
	ActionAllowed        bool   `json:"action_allowed"`
	Prior                string `json:"prior"`
	ClickedInTime        bool   `json:"clicked_in_time"`
	ProcessedInTime      bool   `json:"processed_in_time"`
	SecurityVersionNewer bool   `json:"security_version_newer"`
	Decision             string `json:"decision"`
}

type actionOutcome struct {
	Answer       string  `json:"answer"`
	Reason       *string `json:"reason"`
	Audit        bool    `json:"audit"`
	Record       bool    `json:"record"`
	NotifyHolder bool    `json:"notify_holder"`
}

// actionRecompute reads P20.7's refusals before the grant is the holder's as audit-only, the grant's own outcomes
// after it as recorded and told to the holder, and the kernel's retryable answers as nothing recorded.
func actionRecompute(c actionCase) actionOutcome {
	refuse := func(reason string, final bool) actionOutcome {
		return actionOutcome{Answer: "refused", Reason: &reason, Audit: true, Record: final && reason != "GRANT_USED", NotifyHolder: final}
	}
	switch {
	case !c.ShapeOK:
		return refuse("malformed", false)
	case !c.AudienceIsSelf:
		return actionOutcome{Answer: "ignored"}
	case !c.StreamIsSource:
		return refuse("not_the_sender", false)
	case !c.GrantExists:
		return refuse("unknown_grant", false)
	case !c.PrincipalMatches:
		return refuse("not_the_holder", false)
	case !c.ActionAllowed:
		return refuse("action_not_allowed", false)
	case c.Prior == "same_action":
		return actionOutcome{Answer: "replayed"}
	case c.Prior == "other_action":
		return refuse("GRANT_USED", true)
	case !c.ClickedInTime || !c.ProcessedInTime:
		return refuse("expired", true)
	case c.SecurityVersionNewer:
		return refuse("GRANT_STALE", true)
	}
	switch c.Decision {
	case "approved":
		return actionOutcome{Answer: "executed", Record: true}
	case "view_unprovable", "qualification_unknown", "database_error":
		r := c.Decision
		return actionOutcome{Answer: "retry", Reason: &r}
	}
	return refuse(c.Decision, true)
}

func TestChannelActionVectors(t *testing.T) {
	seen := map[string]bool{}
	for _, raw := range load(t, "channel-action").Cases {
		var v struct {
			ID     string
			Case   actionCase
			Expect actionOutcome
		}
		if err := json.Unmarshal(raw, &v); err != nil {
			t.Fatal(err)
		}
		got := actionRecompute(v.Case)
		if g, w := mustJSON(t, got), mustJSON(t, v.Expect); g != w {
			t.Errorf("%s: recomputed %s, vector %s", v.ID, g, w)
		}
		seen[v.Expect.Answer] = true
	}
	for _, a := range []string{"ignored", "refused", "replayed", "retry", "executed"} {
		if !seen[a] {
			t.Errorf("no vector answers %s", a)
		}
	}
}

func mustJSON(t *testing.T, v any) string {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func channelSchema(t *testing.T, name string) *jsonschema.Schema {
	t.Helper()
	n := "schemas/channel/" + name + ".v1.schema.json"
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

// The action and delivery schemas (P20.2, P20.6): a good event passes; each way of breaking it is refused.
func TestTheChannelSchemas(t *testing.T) {
	action := `"action_id":"0190f3a1-0000-7000-8000-000000000001","channel":"integration/im-dingtalk","audience":"erp/purchase","principal":"u1","grant_id":"0190f3a1-0000-7000-8000-000000000002","action":"approve","clicked_at":"2026-11-13T10:00:00Z"`
	delivery := `"delivery_id":"0190f3a1-0000-7000-8000-000000000003","caller":"infra/notification","sender":"erp/purchase","intent_id":"0190f3a1-0000-7000-8000-000000000004","principal":"u1","result":"sent"`
	for _, c := range []struct {
		schema, name, body string
		ok                 bool
	}{
		{"action", "an action", action, true},
		{"action", "no audience", strings.Replace(action, `"audience":"erp/purchase",`, "", 1), false},
		{"action", "a grant that is not an id", strings.Replace(action, `"0190f3a1-0000-7000-8000-000000000002"`, `"secret"`, 1), false},
		{"action", "an action with a capital", strings.Replace(action, `"approve"`, `"Approve"`, 1), false},
		{"delivery", "a delivery", delivery, true},
		{"delivery", "delivered is not a result", strings.Replace(delivery, `"sent"`, `"delivered"`, 1), false},
		{"delivery", "no intent", strings.Replace(delivery, `"intent_id":"0190f3a1-0000-7000-8000-000000000004",`, "", 1), false},
	} {
		doc, err := jsonschema.UnmarshalJSON(strings.NewReader("{" + c.body + "}"))
		if err != nil {
			t.Fatal(err)
		}
		err = channelSchema(t, c.schema).Validate(doc)
		if (err == nil) != c.ok {
			t.Errorf("%s: valid=%v, want %v (%v)", c.name, err == nil, c.ok, err)
		}
	}
}
