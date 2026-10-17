package protocol

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"reflect"
	"testing"

	"golang.org/x/text/unicode/norm"
)

// refOutcome recomputes the call-outcomes expectations independently of the generator.
func refOutcome(t *testing.T, reasons map[string]string, c map[string]any) map[string]any {
	str := func(k string) string { s, _ := c[k].(string); return s }
	pair := func(k string) (string, string) {
		m, _ := c[k].(map[string]any)
		if m == nil {
			return "", ""
		}
		return m["domain"].(string), m["reason"].(string)
	}
	var code, domain, reason string
	if str("surface") == "grpc" {
		code = str("code")
		domain, reason = pair("info")
	} else {
		domain, reason = pair("problem")
		status, _ := c["status"].(float64)
		switch {
		case domain == "be":
			code = reasons[reason]
		case status == 200:
			code = "OK"
		case status == 502 || status == 503:
			code = "UNAVAILABLE"
		case status == 504:
			code = "DEADLINE_EXCEEDED"
		}
	}
	relayed := domain == "be" && (reason == "DEPENDENCY_UNAVAILABLE" || reason == "CIRCUIT_OPEN" ||
		reason == "DEADLINE_BUDGET_EXHAUSTED" || reason == "RESULT_UNKNOWN")
	class := "other"
	switch {
	case c["caller_cancelled"] == true:
		class = "cancelled"
	case c["connect_failed"] == true:
		class = "connect_failed"
	case code == "OK":
		class = "success"
	case relayed:
		class = "relayed"
	case code == "UNAVAILABLE":
		class = "unavailable"
	case code == "DEADLINE_EXCEEDED":
		class = "deadline"
	}
	dep := map[string]any{"dependency": str("dependency")}
	out := map[string]any{"class": class, "breaker": "ignored", "budget": "other", "retry_outcome": "NONE", "upward": "unchanged"}
	switch class {
	case "success":
		out["breaker"], out["budget"], out["upward"] = "success", "success", nil
	case "unavailable", "connect_failed":
		out["breaker"], out["budget"] = "failure", "unavailable"
		out["retry_outcome"] = map[string]string{"unavailable": "UNAVAILABLE", "connect_failed": "CONNECT_FAILED_BEFORE_SEND"}[class]
		out["upward"] = map[string]any{"domain": "be", "reason": "DEPENDENCY_UNAVAILABLE", "metadata": dep}
	case "deadline":
		out["breaker"] = "failure"
		r := "DEADLINE_EXCEEDED"
		if c["idempotent"] != true {
			r = "RESULT_UNKNOWN"
		}
		out["upward"] = map[string]any{"domain": "be", "reason": r, "metadata": dep}
	case "cancelled":
		out["upward"] = map[string]any{"domain": "be", "reason": "REQUEST_CANCELLED"}
	}
	return out
}

func TestCallOutcomesVectors(t *testing.T) {
	reasons := map[string]string{}
	for _, raw := range load(t, "errors").Cases {
		var c struct {
			Kind, Reason string
			GRPCCode     string `json:"grpc_code"`
		}
		_ = json.Unmarshal(raw, &c)
		if c.Kind == "reason" {
			reasons[c.Reason] = c.GRPCCode
		}
	}
	for _, raw := range load(t, "call-outcomes").Cases {
		var c map[string]any
		_ = json.Unmarshal(raw, &c)
		want := refOutcome(t, reasons, c)
		got := c["expect"].(map[string]any)
		if !reflect.DeepEqual(want, got) {
			t.Errorf("%s: %v, recomputed %v", c["id"], got, want)
		}
	}
}

func TestIdempotencyVectors(t *testing.T) {
	for _, raw := range load(t, "idempotency").Cases {
		var c struct {
			ID, Kind, Key, Principal, Operation, Target, Body, Fingerprint string
			Valid                                                          bool
		}
		_ = json.Unmarshal(raw, &c)
		switch c.Kind {
		case "key":
			valid := len(c.Key) >= 1 && len(c.Key) <= 255
			for i := 0; i < len(c.Key); i++ {
				valid = valid && c.Key[i] >= 0x21 && c.Key[i] <= 0x7e
			}
			if valid != c.Valid {
				t.Errorf("%s: valid %v, the vector says %v", c.ID, valid, c.Valid)
			}
		case "fingerprint":
			sum := sha256.Sum256([]byte(c.Body))
			var buf bytes.Buffer
			refCanonical(&buf, map[string]any{"principal": norm.NFC.String(c.Principal), "operation": norm.NFC.String(c.Operation),
				"target": norm.NFC.String(c.Target), "body_sha256": hex.EncodeToString(sum[:])})
			if got := refDigest("be.idempotency.request", 1, buf.Bytes()); got != c.Fingerprint {
				t.Errorf("%s: fingerprint %s, the vector says %s", c.ID, got, c.Fingerprint)
			}
		default:
			t.Errorf("%s: unknown kind %q", c.ID, c.Kind)
		}
	}
}
