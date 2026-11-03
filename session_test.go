package protocol

import (
	"encoding/json"
	"testing"
)

// P8.25: the subject's version in the view (0 when the subject or the field is absent) above the token's is stale.
func TestTokenStaleVectors(t *testing.T) {
	for _, raw := range load(t, "token-stale").Cases {
		var c struct {
			ID      string
			TokenSV int64 `json:"token_sv"`
			Entry   *struct {
				SecurityVersion *int64 `json:"security_version"`
			}
			Expect struct{ Stale bool }
		}
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		var view int64
		if c.Entry != nil && c.Entry.SecurityVersion != nil {
			view = *c.Entry.SecurityVersion
		}
		if got := view > c.TokenSV; got != c.Expect.Stale {
			t.Errorf("%s: stale %v, the vector says %v", c.ID, got, c.Expect.Stale)
		}
	}
}

type edgeCase struct {
	ID        string
	Method    string
	Cookie    bool
	Headers   map[string]string
	BodyBytes int64 `json:"body_bytes"`
	Cache     string
	Exchange  []string
	Answers   []string
	Expect    edgeOutcome
}

type edgeOutcome struct {
	Browser   string
	Forwarded int
	Exchanges int
	RenewIdle *bool `json:"renew_idle"`
}

// edgeRun is this repository's own reading of P11.1-P11.4 and P11.7, written apart from the generator.
func edgeRun(c edgeCase) edgeOutcome {
	var o edgeOutcome
	answers, exchanges := c.Answers, c.Exchange
	forward := func() string { o.Forwarded++; a := answers[0]; answers = answers[1:]; return a }
	exchange := func() string {
		o.Exchanges++
		renew := c.Headers["BE-Polling"] != "1"
		o.RenewIdle = &renew
		e := exchanges[0]
		exchanges = exchanges[1:]
		return e
	}
	refused := map[string]string{"ended": "SESSION_ENDED", "unavailable": "DEPENDENCY_UNAVAILABLE"}
	if !c.Cookie {
		o.Browser = forward()
		return o
	}
	switch c.Method {
	case "POST", "PUT", "PATCH", "DELETE":
		if c.Headers["BE-Request"] != "1" {
			o.Browser = "CSRF_HEADER_REQUIRED"
			return o
		}
	}
	if c.Cache == "miss" {
		if e := exchange(); e != "ok" {
			o.Browser = refused[e]
			return o
		}
	}
	if o.Browser = forward(); o.Browser != "TOKEN_STALE" {
		return o
	}
	if e := exchange(); e != "ok" {
		o.Browser = refused[e]
		return o
	}
	if c.BodyBytes > 1<<20 {
		o.Browser = "AUTHORIZATION_UNPROVABLE"
		return o
	}
	if o.Browser = forward(); o.Browser == "TOKEN_STALE" {
		o.Browser = "SESSION_ENDED"
	}
	return o
}

func TestEdgeFlowVectors(t *testing.T) {
	for _, raw := range load(t, "edge-flow").Cases {
		var c edgeCase
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		got, want := edgeRun(c), c.Expect
		if got.Browser != want.Browser || got.Forwarded != want.Forwarded || got.Exchanges != want.Exchanges ||
			(got.RenewIdle == nil) != (want.RenewIdle == nil) || got.RenewIdle != nil && *got.RenewIdle != *want.RenewIdle {
			t.Errorf("%s: got %+v, the vector says %+v", c.ID, got, want)
		}
	}
}
