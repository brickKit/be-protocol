package protocol

// The checks here keep the vectors honest: every file has the shape spec/00-reading.md describes, SHA256SUMS matches,
// and every expectation is recomputed by an implementation independent of scripts/gen-vectors.py. These reference
// computations exist only to catch slips in the vectors; SDKs implement the rules themselves.

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io/fs"
	"regexp"
	"strconv"
	"strings"
	"testing"
)

type vectorFile struct {
	Topic       string            `json:"topic"`
	Protocol    string            `json:"protocol"`
	Rules       []string          `json:"rules"`
	Description string            `json:"description"`
	Fields      map[string]string `json:"fields"`
	Cases       []json.RawMessage `json:"cases"`
}

func load(t *testing.T, topic string) vectorFile {
	t.Helper()
	raw, err := fs.ReadFile(Vectors, "vectors/"+topic+".json")
	if err != nil {
		t.Fatal(err)
	}
	var v vectorFile
	if err := json.Unmarshal(raw, &v); err != nil {
		t.Fatalf("%s: %v", topic, err)
	}
	return v
}

func TestEveryVectorFileIsWellFormed(t *testing.T) {
	entries, err := fs.ReadDir(Vectors, "vectors")
	if err != nil {
		t.Fatal(err)
	}
	ruleID := regexp.MustCompile(`^P[0-9]+\.[0-9]+$`)
	n := 0
	for _, e := range entries {
		if !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		n++
		topic := strings.TrimSuffix(e.Name(), ".json")
		v := load(t, topic)
		if v.Topic != topic || v.Protocol != Version || v.Description == "" || len(v.Fields) == 0 || len(v.Cases) == 0 {
			t.Errorf("%s: topic, protocol (%s), description, fields and cases are all required", e.Name(), Version)
		}
		for _, r := range v.Rules {
			if !ruleID.MatchString(r) {
				t.Errorf("%s: rule id %q", e.Name(), r)
			}
		}
		seen := map[string]bool{}
		for _, c := range v.Cases {
			var head struct {
				ID string `json:"id"`
			}
			if err := json.Unmarshal(c, &head); err != nil || head.ID == "" || seen[head.ID] {
				t.Errorf("%s: every case needs a unique id (%q)", e.Name(), head.ID)
			}
			seen[head.ID] = true
		}
	}
	if n == 0 {
		t.Fatal("no vector files")
	}
}

func TestSHA256SUMS(t *testing.T) {
	f, err := Vectors.Open("vectors/SHA256SUMS")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	listed := map[string]bool{}
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		sum, name, ok := strings.Cut(sc.Text(), "  ")
		if !ok {
			t.Fatalf("bad line %q", sc.Text())
		}
		raw, err := fs.ReadFile(Vectors, "vectors/"+name)
		if err != nil {
			t.Fatal(err)
		}
		got := sha256.Sum256(raw)
		if hex.EncodeToString(got[:]) != sum {
			t.Errorf("%s: SHA256SUMS is stale (run scripts/gen-vectors.py)", name)
		}
		listed[name] = true
	}
	entries, _ := fs.ReadDir(Vectors, "vectors")
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".json") && !listed[e.Name()] {
			t.Errorf("%s is not in SHA256SUMS", e.Name())
		}
	}
}

// ---------------------------------------------------------------- errors

var codeHTTP = map[string]int{"INVALID_ARGUMENT": 400, "FAILED_PRECONDITION": 400, "OUT_OF_RANGE": 400,
	"UNAUTHENTICATED": 401, "PERMISSION_DENIED": 403, "NOT_FOUND": 404, "ALREADY_EXISTS": 409, "ABORTED": 409,
	"RESOURCE_EXHAUSTED": 429, "CANCELLED": 499, "INTERNAL": 500, "UNKNOWN": 500, "DATA_LOSS": 500,
	"UNIMPLEMENTED": 501, "UNAVAILABLE": 503, "DEADLINE_EXCEEDED": 504}

func logLevel(code string) string {
	switch code {
	case "INTERNAL", "UNKNOWN", "DATA_LOSS":
		return "error"
	case "UNAVAILABLE", "DEADLINE_EXCEEDED":
		return "warn"
	case "CANCELLED":
		return "none"
	}
	return "info"
}

func TestErrorsVectors(t *testing.T) {
	overrides := map[string]int{"BODY_TOO_LARGE": 413, "QUERY_NOT_COMPLETABLE": 422, "FIELD_NOT_QUERYABLE": 422,
		"LAST_ADMIN_PROTECTED": 409, "IDEMPOTENCY_KEY_REUSED": 422, "OUTBOUND_LIMIT": 503}
	for _, raw := range load(t, "errors").Cases {
		var c struct {
			ID, Kind, Reason, Domain, Type string
			GRPCCode                       string `json:"grpc_code"`
			HTTP                           int
			LogLevel                       string `json:"log_level"`
		}
		_ = json.Unmarshal(raw, &c)
		switch c.Kind {
		case "reason":
			want, ok := overrides[c.Reason]
			if !ok {
				want = codeHTTP[c.GRPCCode]
			}
			if c.HTTP != want || c.LogLevel != logLevel(c.GRPCCode) || c.Domain != "be" || c.Type != "urn:be:be:"+c.Reason {
				t.Errorf("%s: http %d (want %d), log %s, domain %s, type %s", c.ID, c.HTTP, want, c.LogLevel, c.Domain, c.Type)
			}
		case "code":
			if c.HTTP != codeHTTP[c.GRPCCode] || c.LogLevel != logLevel(c.GRPCCode) {
				t.Errorf("%s", c.ID)
			}
		case "access_log":
			want := "info"
			if c.HTTP == 500 {
				want = "error"
			} else if c.HTTP == 503 || c.HTTP == 504 {
				want = "warn"
			}
			if c.LogLevel != want {
				t.Errorf("%s: %s, want %s", c.ID, c.LogLevel, want)
			}
		default:
			t.Errorf("%s: kind %q", c.ID, c.Kind)
		}
	}
}

// ---------------------------------------------------------------- outbound timeout, retry decision

func TestOutboundTimeoutVectors(t *testing.T) {
	for _, raw := range load(t, "outbound-timeout").Cases {
		var c struct {
			ID        string
			Remaining *int `json:"remaining_ms"`
			Expect    struct {
				Send    bool
				Timeout int `json:"timeout_ms"`
				Reason  string
			}
		}
		_ = json.Unmarshal(raw, &c)
		send := c.Remaining != nil && *c.Remaining >= 50
		if c.Expect.Send != send {
			t.Errorf("%s: send %v", c.ID, c.Expect.Send)
			continue
		}
		if send && c.Expect.Timeout != min(3000, *c.Remaining-50) {
			t.Errorf("%s: timeout %d", c.ID, c.Expect.Timeout)
		}
		if !send && c.Expect.Reason != "DEADLINE_BUDGET_EXHAUSTED" {
			t.Errorf("%s: reason %s", c.ID, c.Expect.Reason)
		}
	}
}

func TestRetryDecisionVectors(t *testing.T) {
	for _, raw := range load(t, "retry-decision").Cases {
		var c struct {
			ID, Kind, Outcome, Expect string
			Idempotent                bool
			AttemptsMade              int  `json:"attempts_made"`
			BudgetAllows              bool `json:"budget_allows"`
			After                     *int `json:"remaining_ms_after_backoff"`
			Failed                    int  `json:"failed_attempts"`
			MaxBackoff                int  `json:"max_backoff_ms"`
		}
		_ = json.Unmarshal(raw, &c)
		if c.Kind == "backoff" {
			if want := min(1000, 100<<(c.Failed-1)); c.MaxBackoff != want {
				t.Errorf("%s: %d, want %d", c.ID, c.MaxBackoff, want)
			}
			continue
		}
		want := "stop"
		if c.Idempotent && (c.Outcome == "UNAVAILABLE" || c.Outcome == "CONNECT_FAILED_BEFORE_SEND") &&
			c.AttemptsMade < 3 && c.BudgetAllows && c.After != nil && *c.After >= 50 {
			want = "retry"
		}
		if c.Expect != want {
			t.Errorf("%s: %s, want %s", c.ID, c.Expect, want)
		}
	}
}

// ---------------------------------------------------------------- retry budget

func TestRetryBudgetVectors(t *testing.T) {
	for _, raw := range load(t, "retry-budget").Cases {
		var c struct {
			ID      string
			Events  []string
			Tokens  []int  `json:"expect_tokens"`
			Allowed []bool `json:"expect_retry_allowed"`
			Final   bool   `json:"expect_final_retry_allowed"`
		}
		_ = json.Unmarshal(raw, &c)
		tokens := 10000
		for i, e := range c.Events {
			switch e {
			case "success":
				tokens = min(10000, tokens+100)
			case "unavailable":
				tokens = max(0, tokens-1000)
			}
			if c.Tokens[i] != tokens || c.Allowed[i] != (tokens > 5000) {
				t.Errorf("%s step %d: tokens %d allowed %v, want %d %v", c.ID, i, c.Tokens[i], c.Allowed[i], tokens, tokens > 5000)
			}
		}
		if c.Final != (tokens > 5000) {
			t.Errorf("%s: final", c.ID)
		}
	}
}

// ---------------------------------------------------------------- circuit breaker

type refBreaker struct {
	state    string
	results  []bool // true = dependency failure
	openedAt int
	trial    string
	trialOK  int
}

func (b *refBreaker) start(now int, call string) string {
	if b.state == "open" {
		if now-b.openedAt < 30000 {
			return "rejected"
		}
		b.state, b.trial, b.trialOK = "half_open", "", 0
	}
	if b.state == "half_open" {
		if b.trial != "" {
			return "rejected"
		}
		b.trial = call
	}
	return "sent"
}

func (b *refBreaker) end(now int, call, outcome string) {
	switch {
	case outcome == "ignored":
		if b.state == "half_open" && b.trial == call {
			b.trial = ""
		}
	case b.state == "half_open":
		if b.trial != call {
			return
		}
		b.trial = ""
		if outcome == "failure" {
			b.state, b.openedAt, b.trialOK = "open", now, 0
			return
		}
		if b.trialOK++; b.trialOK >= 3 {
			b.state, b.results = "closed", nil
		}
	case b.state == "closed":
		b.results = append(b.results, outcome == "failure")
		if len(b.results) > 20 {
			b.results = b.results[len(b.results)-20:]
		}
		failures := 0
		for _, f := range b.results {
			if f {
				failures++
			}
		}
		if len(b.results) == 20 && failures*2 > 20 {
			b.state, b.openedAt, b.results = "open", now, nil
		}
	}
}

func TestCircuitBreakerVectors(t *testing.T) {
	for _, raw := range load(t, "circuit-breaker").Cases {
		var c struct {
			ID    string
			Steps []struct {
				At                          int `json:"at_ms"`
				Kind, Call, Outcome, Expect string
				ExpectState                 string `json:"expect_state"`
			}
		}
		_ = json.Unmarshal(raw, &c)
		b := &refBreaker{state: "closed"}
		for i, s := range c.Steps {
			if s.Kind == "start" {
				if got := b.start(s.At, s.Call); got != s.Expect {
					t.Errorf("%s step %d: %s, want %s", c.ID, i, s.Expect, got)
				}
			} else {
				b.end(s.At, s.Call, s.Outcome)
			}
			if b.state != s.ExpectState {
				t.Errorf("%s step %d: state %s, want %s", c.ID, i, s.ExpectState, b.state)
			}
		}
	}
}

// ---------------------------------------------------------------- config parse

func refParse(typ string, v *string, required bool, def any, values []string) (any, string) {
	if v == nil || *v == "" {
		if required {
			return nil, "missing"
		}
		return def, ""
	}
	s := *v
	switch typ {
	case "string":
		return s, ""
	case "integer":
		if !regexp.MustCompile(`^-?(0|[1-9][0-9]*)$`).MatchString(s) || s == "-0" {
			return nil, "invalid"
		}
		n, _ := strconv.Atoi(s)
		return float64(n), ""
	case "boolean":
		if s != "true" && s != "false" {
			return nil, "invalid"
		}
		return s == "true", ""
	case "duration":
		m := regexp.MustCompile(`^(0|[1-9][0-9]*)(ms|s|m|h)$`).FindStringSubmatch(s)
		if m == nil {
			return nil, "invalid"
		}
		n, _ := strconv.Atoi(m[1])
		return float64(n * map[string]int{"ms": 1, "s": 1000, "m": 60000, "h": 3600000}[m[2]]), ""
	case "enum":
		for _, x := range values {
			if x == s {
				return s, ""
			}
		}
		return nil, "unknown_enum"
	}
	return nil, "unknown type " + typ
}

func TestConfigParseVectors(t *testing.T) {
	for _, raw := range load(t, "config-parse").Cases {
		var c struct {
			ID, Type string
			Value    *string
			Required bool
			Default  any
			Values   []string
			Expect   struct {
				Value any
				Error string
			}
		}
		_ = json.Unmarshal(raw, &c)
		got, errKind := refParse(c.Type, c.Value, c.Required, c.Default, c.Values)
		if errKind != c.Expect.Error || (errKind == "" && got != c.Expect.Value) {
			t.Errorf("%s: vector says %v/%q, reference gives %v/%q", c.ID, c.Expect.Value, c.Expect.Error, got, errKind)
		}
	}
}
