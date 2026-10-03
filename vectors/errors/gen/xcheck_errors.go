//go:build ignore

// xcheck_errors recomputes vectors/errors/*.json in Go from tables typed in
// again from foundations 15 and sdk-redesign P4 / P10.4 (no shared code).
//
//	docker run --rm -v "$PWD":/v -w /v golang:1.22-alpine go run errors/gen/xcheck_errors.go errors
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
)

// canonical gRPC codes in numeric order (google.golang.org/grpc/codes)
var codes = []string{"OK", "CANCELLED", "UNKNOWN", "INVALID_ARGUMENT", "DEADLINE_EXCEEDED", "NOT_FOUND",
	"ALREADY_EXISTS", "PERMISSION_DENIED", "RESOURCE_EXHAUSTED", "FAILED_PRECONDITION", "ABORTED", "OUT_OF_RANGE",
	"UNIMPLEMENTED", "INTERNAL", "UNAVAILABLE", "DATA_LOSS", "UNAUTHENTICATED"}

// foundations 15, "gRPC form" table
func statusOf(code string) (int, bool) {
	switch code {
	case "OK":
		return 200, true
	case "INVALID_ARGUMENT", "FAILED_PRECONDITION", "OUT_OF_RANGE":
		return 400, true
	case "UNAUTHENTICATED":
		return 401, true
	case "PERMISSION_DENIED":
		return 403, true
	case "NOT_FOUND":
		return 404, true
	case "ALREADY_EXISTS", "ABORTED":
		return 409, true
	case "INTERNAL", "UNKNOWN", "DATA_LOSS":
		return 500, true
	case "RESOURCE_EXHAUSTED":
		return 429, true
	case "CANCELLED":
		return 499, true
	case "UNIMPLEMENTED":
		return 501, true
	case "UNAVAILABLE":
		return 503, true
	case "DEADLINE_EXCEEDED":
		return 504, true
	}
	return 0, false
}

var beReasons = map[string]string{
	"INTERNAL": "INTERNAL", "TOKEN_STALE": "UNAUTHENTICATED", "MISSING_PERMISSION": "PERMISSION_DENIED",
	"NOT_FOUND": "NOT_FOUND", "AUTHZ_NOT_READY": "UNAVAILABLE", "NOT_READY": "UNAVAILABLE", "TOKEN_INVALID": "UNAUTHENTICATED",
	"UNSUPPORTED_DELEGATION": "UNAUTHENTICATED", "MISSING_CALLER": "UNAUTHENTICATED", "OUT_OF_SCOPE": "PERMISSION_DENIED",
	"FIELD_FORBIDDEN": "PERMISSION_DENIED", "SORT_FORBIDDEN": "INVALID_ARGUMENT", "SHARE_NOT_ALLOWED": "PERMISSION_DENIED",
	"CAPABILITY_UNAVAILABLE": "UNIMPLEMENTED", "IDEMPOTENCY_MISMATCH": "INVALID_ARGUMENT", "IDEMPOTENCY_IN_PROGRESS": "ABORTED",
	"CURSOR_INVALID": "INVALID_ARGUMENT", "BATCH_TOO_LARGE": "INVALID_ARGUMENT", "LOCK_TIMEOUT": "ABORTED",
	"STATEMENT_TIMEOUT": "DEADLINE_EXCEEDED", "TX_CONFLICT": "ABORTED", "DB_POOL_EXHAUSTED": "RESOURCE_EXHAUSTED",
	"OUTBOUND_LIMIT": "RESOURCE_EXHAUSTED", "DEADLINE_BUDGET_EXHAUSTED": "DEADLINE_EXCEEDED", "BODY_TOO_LARGE": "INVALID_ARGUMENT",
	"RANGE_COLD": "FAILED_PRECONDITION", "UNIT_SEALED": "FAILED_PRECONDITION",
	"RATE_LIMITED": "RESOURCE_EXHAUSTED", "UPSTREAM_UNAVAILABLE": "UNAVAILABLE", "UPSTREAM_TIMEOUT": "DEADLINE_EXCEEDED",
	"NETWORK_IN_TX": "INTERNAL", "DB_TOO_MANY_CONNECTIONS": "UNAVAILABLE", "NESTED_TX": "INTERNAL",
	"REQUEST_INVALID": "INVALID_ARGUMENT", "DEPENDENCY_UNAVAILABLE": "UNAVAILABLE", "REQUEST_CANCELLED": "CANCELLED",
}

type fail string

// a lost or refused database connection (P4: DEPENDENCY_UNAVAILABLE naming the database)
func dbDown() map[string]any {
	m := failRes("UNAVAILABLE", "DEPENDENCY_UNAVAILABLE", "be", 503)
	m["metadata"] = map[string]any{"dependency": "db"}
	return m
}

func httpOf(code, reason, domain string) int {
	s, ok := statusOf(code)
	if !ok {
		panic(fail("CODE_UNKNOWN"))
	}
	if reason == "BODY_TOO_LARGE" && domain == "be" {
		return 413
	}
	return s
}

func str(m map[string]any, k string) string { s, _ := m[k].(string); return s }

func num(v int) float64 { return float64(v) }

func failRes(code string, reason, domain any, http int) map[string]any {
	return map[string]any{"action": "fail", "code": code, "reason": reason, "domain": domain, "http": num(http)}
}

var reasonRe = regexp.MustCompile(`^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$`)

func run(op string, in map[string]any) any {
	switch op {
	case "grpc_to_http":
		c := str(in, "code")
		h := httpOf(c, str(in, "reason"), str(in, "domain"))
		for i, x := range codes {
			if x == c {
				return map[string]any{"number": num(i), "http": num(h)}
			}
		}
	case "be_reason":
		c := beReasons[str(in, "reason")]
		return map[string]any{"code": c, "domain": "be", "http": num(httpOf(c, str(in, "reason"), "be"))}
	case "restore_http":
		st := int(in["status"].(float64))
		if pb, ok := in["problem"].(map[string]any); ok {
			if _, known := statusOf(str(pb, "code")); known && str(pb, "reason") != "" && str(pb, "domain") != "" {
				return map[string]any{"code": pb["code"], "reason": pb["reason"], "domain": pb["domain"], "http": num(st)}
			}
		}
		code := "UNKNOWN"
		switch {
		case st == 400 || st == 413:
			code = "INVALID_ARGUMENT"
		case st == 401:
			code = "UNAUTHENTICATED"
		case st == 403:
			code = "PERMISSION_DENIED"
		case st == 404:
			code = "NOT_FOUND"
		case st == 409:
			code = "ABORTED"
		case st == 429:
			code = "RESOURCE_EXHAUSTED"
		case st == 499:
			code = "CANCELLED"
		case st == 501:
			code = "UNIMPLEMENTED"
		case st == 502 || st == 503:
			code = "UNAVAILABLE"
		case st == 504:
			code = "DEADLINE_EXCEEDED"
		case st >= 400 && st < 500:
			code = "FAILED_PRECONDITION"
		}
		return map[string]any{"code": code, "reason": nil, "domain": nil, "http": num(st)}
	case "classify":
		s := str(in, "sqlstate")
		attempt := 1
		if a, ok := in["attempt"].(float64); ok {
			attempt = int(a)
		}
		if len(s) == 5 && s[:2] == "08" {
			return dbDown()
		}
		switch s {
		case "40001", "40P01":
			if attempt <= 2 {
				return map[string]any{"action": "retry", "base_delay_ms": num(10 << (attempt - 1))}
			}
			return failRes("ABORTED", "TX_CONFLICT", "be", 409)
		case "55P03":
			return failRes("ABORTED", "LOCK_TIMEOUT", "be", 409)
		case "57014":
			if str(in, "context") == "cancelled" {
				return failRes("CANCELLED", "REQUEST_CANCELLED", "be", 499)
			}
			return failRes("DEADLINE_EXCEEDED", "STATEMENT_TIMEOUT", "be", 504)
		case "25P04":
			return failRes("DEADLINE_EXCEEDED", "STATEMENT_TIMEOUT", "be", 504)
		case "53300":
			return failRes("UNAVAILABLE", "DB_TOO_MANY_CONNECTIONS", "be", 503)
		case "57P01", "57P02", "57P03":
			return dbDown()
		case "23505":
			if m, ok := in["component_mapping"].(map[string]any); ok {
				return failRes(str(m, "code"), m["reason"], m["domain"], httpOf(str(m, "code"), "", ""))
			}
		}
		return failRes("INTERNAL", "INTERNAL", "be", 500)
	case "log_level":
		switch str(in, "code") {
		case "INTERNAL", "UNKNOWN", "DATA_LOSS":
			return map[string]any{"level": "error"}
		case "UNAVAILABLE", "DEADLINE_EXCEEDED":
			return map[string]any{"level": "warn"}
		case "CANCELLED", "OK":
			return map[string]any{"level": "none"}
		}
		return map[string]any{"level": "info"}
	case "access_log_level":
		switch str(in, "code") {
		case "INTERNAL", "UNKNOWN", "DATA_LOSS":
			return map[string]any{"level": "error"}
		case "UNAVAILABLE", "DEADLINE_EXCEEDED":
			return map[string]any{"level": "warn"}
		}
		return map[string]any{"level": "info"}
	case "problem":
		e, rq := in["error"].(map[string]any), in["request"].(map[string]any)
		code := str(e, "code")
		if code == "" {
			code = "INTERNAL"
		}
		if _, ok := statusOf(code); !ok || code == "OK" {
			panic(fail("CODE_UNKNOWN"))
		}
		reason, domain := str(e, "reason"), str(e, "domain")
		meta, _ := e["metadata"].(map[string]any)
		viol := e["violations"]
		hidden := code == "INTERNAL" || code == "UNKNOWN" || code == "DATA_LOSS" || reason == "" || domain == ""
		if hidden {
			if code != "UNKNOWN" && code != "DATA_LOSS" {
				code = "INTERNAL"
			}
			reason, domain, meta, viol = "INTERNAL", "be", nil, nil
		}
		m := map[string]any{}
		for k, v := range meta {
			if _, ok := v.(string); !ok {
				panic(fail("METADATA_NOT_STRING"))
			}
			m[k] = v
		}
		body := map[string]any{"type": "urn:be:" + domain + ":" + reason, "status": num(httpOf(code, reason, domain)),
			"code": code, "reason": reason, "domain": domain, "metadata": m, "instance": rq["path"],
			"request_id": rq["request_id"], "trace_id": rq["trace_id"]}
		if viol != nil {
			body["violations"] = viol
		}
		out := map[string]any{"content_type": "application/problem+json", "body": body}
		if s := str(e, "internal_message"); hidden && s != "" {
			out["detail_must_not_contain"] = []any{s}
		}
		return out
	case "retry_after":
		ms, _ := in["retry_delay_ms"].(float64)
		c := str(in, "code")
		if (c != "RESOURCE_EXHAUSTED" && c != "UNAVAILABLE") || ms <= 0 {
			return map[string]any{"header": nil}
		}
		return map[string]any{"header": fmt.Sprint((int(ms) + 999) / 1000)}
	case "reason_name":
		r := str(in, "reason")
		if !reasonRe.MatchString(r) {
			panic(fail("REASON_NAME_INVALID"))
		}
		if _, reserved := beReasons[r]; reserved && str(in, "domain") != "be" {
			panic(fail("REASON_RESERVED"))
		}
		return map[string]any{"valid": true}
	}
	panic("op " + op)
}

func exec(op string, in map[string]any) (res any, reason string) {
	defer func() {
		if r := recover(); r != nil {
			if f, ok := r.(fail); ok {
				reason = string(f)
				return
			}
			panic(r)
		}
	}()
	return run(op, in), ""
}

func main() {
	bad, n := 0, 0
	files, _ := filepath.Glob(filepath.Join(os.Args[1], "*.json"))
	for _, f := range files {
		b, _ := os.ReadFile(f)
		var doc struct{ Cases []map[string]any }
		if err := json.Unmarshal(b, &doc); err != nil {
			panic(err)
		}
		for _, c := range doc.Cases {
			n++
			res, reason := exec(c["op"].(string), c["input"].(map[string]any))
			var got, want any = res, c["expected"]
			if e, ok := c["expected_error"]; ok {
				got, want = map[string]any{"reason": reason}, e
			}
			if !reflect.DeepEqual(got, want) {
				bad++
				fmt.Printf("DISAGREE %s:\n  want %v\n  go   %v %s\n", c["id"], want, res, reason)
			}
		}
	}
	fmt.Printf("errors xcheck: %d cases, %d disagreements\n", n, bad)
	if bad > 0 {
		os.Exit(1)
	}
}
