//go:build ignore

// xcheck_config recomputes vectors/config/*.json in Go. Durations go
// through the standard library's time.ParseDuration, URLs through net/url,
// JSON through encoding/json: the vectors' rules are layered on top of the
// libraries a Go SDK would use, so a disagreement shows where a library's
// default behaviour differs from the protocol.
//
//	docker run --rm -v "$PWD":/v -w /v golang:1.22-alpine go run config/gen/xcheck_config.go config
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"strconv"
	"strings"
	"time"
)

type cfgErr string

func bad(r string) { panic(cfgErr(r)) }

func s(m map[string]any, k string) (string, bool) { v, ok := m[k].(string); return v, ok }

func dur(v string) int64 {
	d, err := time.ParseDuration(v)
	if err != nil {
		bad("CONFIG_INVALID")
	}
	return int64(d)
}

// strict JSON: duplicate names and non-JSON tokens are rejected
func strictJSON(v string) any {
	dec := json.NewDecoder(strings.NewReader(v))
	dec.UseNumber()
	var walk func() any
	walk = func() any {
		t, err := dec.Token()
		if err != nil {
			bad("CONFIG_INVALID")
		}
		switch x := t.(type) {
		case json.Delim:
			if x == '{' {
				m := map[string]any{}
				for dec.More() {
					k, err := dec.Token()
					if err != nil {
						bad("CONFIG_INVALID")
					}
					ks := k.(string)
					if _, dup := m[ks]; dup {
						bad("CONFIG_INVALID")
					}
					m[ks] = walk()
				}
				dec.Token()
				return m
			}
			if x == '[' {
				a := []any{}
				for dec.More() {
					a = append(a, walk())
				}
				dec.Token()
				return a
			}
		case json.Number:
			f, _ := x.Float64()
			return f
		}
		return t
	}
	out := walk()
	if dec.More() {
		bad("CONFIG_INVALID")
	}
	if _, err := dec.Token(); err == nil {
		bad("CONFIG_INVALID")
	}
	return out
}

var intRe = regexp.MustCompile(`^-?[0-9]+$`)

func parseValue(in map[string]any) any {
	t, _ := s(in, "type")
	v, has := s(in, "value")
	if has && v == "" {
		has = false
	}
	if !has {
		if d, ok := s(in, "default"); ok {
			v = d
		} else if req, _ := in["required"].(bool); req {
			bad("CONFIG_MISSING")
		} else {
			return map[string]any{"set": false}
		}
	}
	var out any
	switch t {
	case "string":
		out = v
	case "integer":
		if !intRe.MatchString(v) {
			bad("CONFIG_INVALID")
		}
		n, err := strconv.ParseInt(v, 10, 64)
		if err != nil || n > 1<<53-1 || n < -(1<<53-1) {
			bad("CONFIG_INVALID")
		}
		if min, ok := in["minimum"].(float64); ok && float64(n) < min {
			bad("CONFIG_INVALID")
		}
		out = float64(n)
	case "boolean":
		switch v {
		case "true", "1":
			out = true
		case "false", "0":
			out = false
		default:
			bad("CONFIG_INVALID")
		}
	case "duration":
		d := dur(v)
		if d < 0 {
			bad("CONFIG_INVALID")
		}
		out = strconv.FormatInt(d, 10)
	case "duration_list":
		var l []any
		for _, p := range strings.Split(v, ",") {
			if p == "" || strings.TrimSpace(p) != p {
				bad("CONFIG_INVALID")
			}
			d := dur(p)
			if d <= 0 {
				bad("CONFIG_INVALID")
			}
			l = append(l, strconv.FormatInt(d, 10))
		}
		out = l
	case "url":
		u, err := url.Parse(v)
		if err != nil || u.Scheme == "" || !strings.HasPrefix(v, u.Scheme+"://") || u.Host == "" ||
			strings.ContainsAny(v, " \t\r\n") || strings.Contains(u.Host, ",") {
			bad("CONFIG_INVALID")
		}
		if p := u.Port(); p != "" {
			n, err := strconv.Atoi(p)
			if err != nil || n < 1 || n > 65535 {
				bad("CONFIG_INVALID")
			}
		}
		if sc, ok := in["schemes"].([]any); ok {
			found := false
			for _, x := range sc {
				found = found || x == u.Scheme
			}
			if !found {
				bad("CONFIG_INVALID")
			}
		}
		out = v
	case "json":
		out = strictJSON(v)
		switch in["json_kind"] {
		case "object":
			if _, ok := out.(map[string]any); !ok {
				bad("CONFIG_INVALID")
			}
		case "array":
			if _, ok := out.([]any); !ok {
				bad("CONFIG_INVALID")
			}
		}
	case "enum":
		ok := false
		for _, e := range in["enum"].([]any) {
			ok = ok || e == v
		}
		if !ok {
			bad("CONFIG_INVALID")
		}
		out = v
	}
	if sec, _ := in["secret"].(bool); sec {
		// a secret is delivered as a file: the variable holds an absolute path, never the value
		if t != "string" || !filepath.IsAbs(v) || strings.HasSuffix(v, "/") || strings.ContainsRune(v, 0) {
			bad("CONFIG_INVALID")
		}
		return map[string]any{"set": true, "source": "file", "path": v}
	}
	return map[string]any{"set": true, "value": out}
}

var (
	compRe = regexp.MustCompile(`^[a-z][a-z0-9]*/[a-z][a-z0-9-]*$`)
	portRe = regexp.MustCompile(`^[a-z][a-z0-9-]*$`)
	hostRe = regexp.MustCompile(`^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$`)
	keyRe  = regexp.MustCompile(`^[A-Z][A-Z0-9_]*$`)
	refRe  = regexp.MustCompile(`\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^${}]*))?\}`)
	nameRe = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)
)

func run(op string, in map[string]any) any {
	switch op {
	case "parse_value":
		return parseValue(in)
	case "read_undeclared":
		k, _ := s(in, "key")
		if k == "COMPONENT_ID" || k == "COMPONENT_VERSION" || k == "PORT" || strings.HasSuffix(k, "_ENDPOINT") {
			return map[string]any{"allowed": true}
		}
		bad("CONFIG_UNDECLARED")
	case "endpoint_name":
		dep, _ := s(in, "dependency")
		port, _ := s(in, "port")
		if !compRe.MatchString(dep) {
			bad("COMPONENT_INVALID")
		}
		n := strings.NewReplacer("/", "_", "-", "_").Replace(strings.ToUpper(dep))
		if port != "" {
			if !portRe.MatchString(port) {
				bad("PORT_NAME_INVALID")
			}
			n += "_" + strings.ReplaceAll(strings.ToUpper(port), "-", "_")
		}
		return map[string]any{"name": n + "_ENDPOINT"}
	case "endpoint_value":
		v, ok := s(in, "value")
		if !ok {
			return map[string]any{"present": false}
		}
		rest, ok := strings.CutPrefix(v, "http://")
		if !ok {
			bad("CONFIG_INVALID")
		}
		rest = strings.TrimRight(rest, "/")
		h, p, found := strings.Cut(rest, ":")
		n, err := strconv.Atoi(p)
		if !found || !hostRe.MatchString(h) || err != nil || n < 1 || n > 65535 || len(p) > 5 {
			bad("CONFIG_INVALID")
		}
		return map[string]any{"present": true, "address": rest}
	case "secret_text":
		c, _ := s(in, "content")
		if x, ok := strings.CutSuffix(c, "\r\n"); ok {
			c = x
		} else {
			c = strings.TrimSuffix(c, "\n")
		}
		if c == "" {
			if req, _ := in["required"].(bool); req {
				bad("CONFIG_MISSING")
			}
			return map[string]any{"set": false}
		}
		return map[string]any{"set": true, "value": c}
	case "family_address":
		k, _ := s(in, "key")
		kind, known := map[string]string{"AUTHZ_URL": "http", "AUTHZ_GRPC_URL": "grpc", "IAM_URL": "http", "IAM_GRPC_URL": "grpc"}[k]
		if !known {
			bad("CONFIG_KEY_INVALID")
		}
		v, ok := s(in, "value")
		if !ok {
			return map[string]any{"present": false}
		}
		u, err := url.Parse(v)
		if err != nil || u.Scheme != "http" || !strings.HasPrefix(v, "http://") || u.User != nil || u.RawQuery != "" ||
			u.Fragment != "" || strings.Trim(u.Path, "/") != "" || !hostRe.MatchString(u.Hostname()) {
			bad("CONFIG_INVALID")
		}
		n, err := strconv.Atoi(u.Port())
		if err != nil || n < 1 || n > 65535 || len(u.Port()) > 5 {
			bad("CONFIG_INVALID")
		}
		if kind == "grpc" {
			return map[string]any{"present": true, "target": u.Host}
		}
		return map[string]any{"present": true, "base": "http://" + u.Host}
	case "key_declaration":
		k, _ := s(in, "key")
		run("key_name", map[string]any{"key": k})
		secret, _ := in["secret"].(bool)
		mount, hasMount := s(in, "mount")
		t, ok := s(in, "type")
		if !ok {
			t = "string"
		}
		switch {
		case hasMount && mount != "file":
			bad("MOUNT_INVALID")
		case hasMount && !secret:
			bad("MOUNT_NEEDS_SECRET")
		case hasMount && t != "string":
			bad("MOUNT_NEEDS_STRING")
		case secret && !hasMount:
			bad("SECRET_NOT_FILE")
		case secret && !strings.HasSuffix(k, "_FILE"):
			bad("FILE_SUFFIX_REQUIRED")
		case !secret && strings.HasSuffix(k, "_FILE"):
			bad("FILE_SUFFIX_RESERVED")
		}
		return map[string]any{"valid": true}
	case "key_name":
		k, _ := s(in, "key")
		if !keyRe.MatchString(k) {
			bad("CONFIG_KEY_INVALID")
		}
		if k == "COMPONENT_ID" || k == "COMPONENT_VERSION" || k == "PORT" || strings.HasSuffix(k, "_ENDPOINT") ||
			strings.HasPrefix(k, "BRICKKIT_SERVED_MEMBERS") {
			bad("CONFIG_KEY_RESERVED")
		}
		return map[string]any{"valid": true}
	case "value_form":
		secret, _ := in["secret"].(bool)
		switch w := in["written"].(type) {
		case map[string]any:
			n, ok1 := w["existingSecret"].(string)
			k, ok2 := w["key"].(string)
			if len(w) != 2 || !ok1 || !ok2 || n == "" || k == "" {
				bad("FORM_INVALID")
			}
			if !secret {
				bad("FORM_NOT_FOR_PLAIN")
			}
			return map[string]any{"form": "existing_secret", "name": n, "key": k}
		case string:
			if name, ok := strings.CutPrefix(w, "$var:"); ok {
				if !nameRe.MatchString(name) {
					bad("FORM_INVALID")
				}
				return map[string]any{"form": "var", "name": name}
			}
			if ref, ok := strings.CutPrefix(w, "$endpoint:"); ok {
				out := endpointForm(ref)
				if secret {
					bad("SECRET_NOT_REFERENCE")
				}
				return out
			}
			if p, ok := strings.CutPrefix(w, "file://"); ok {
				if p == "" || strings.HasPrefix(p, "/") {
					bad("FORM_INVALID")
				}
				for _, seg := range strings.Split(p, "/") {
					if seg == ".." {
						bad("FORM_INVALID")
					}
				}
				return map[string]any{"form": "file", "path": p}
			}
			if m := refRe.FindStringSubmatchIndex(w); m != nil && m[0] == 0 && m[1] == len(w) {
				sm := refRe.FindStringSubmatch(w)
				if m[4] >= 0 {
					if secret && sm[3] != "" {
						bad("SECRET_PLAINTEXT_DEFAULT")
					}
					return map[string]any{"form": "env", "name": sm[1], "default": sm[3]}
				}
				return map[string]any{"form": "env", "name": sm[1]}
			}
			rest := refRe.ReplaceAllString(w, "")
			if strings.Contains(rest, "${") || strings.Contains(w, "$var:") || strings.Contains(w, "$endpoint:") {
				bad("FORM_INVALID")
			}
			if secret {
				bad("SECRET_NOT_REFERENCE")
			}
			if rest != w {
				var names []any
				for _, sm := range refRe.FindAllStringSubmatch(w, -1) {
					names = append(names, sm[1])
				}
				return map[string]any{"form": "template", "names": names}
			}
			return map[string]any{"form": "literal"}
		}
		bad("FORM_INVALID")
	}
	panic("op " + op)
}

var (
	idSegRe   = regexp.MustCompile(`^[a-z][a-z0-9]*$`)
	nameSegRe = regexp.MustCompile(`^[a-z][a-z0-9-]*$`)
	verRe     = regexp.MustCompile(`^\d+\.\d+\.\d+$`)
	portNmRe  = regexp.MustCompile(`^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`)
)

// endpointForm follows brickKit's parseEndpointRef: <scope>/<name>[@<version>][:<port>][/<path>]
func endpointForm(ref string) map[string]any {
	scope, rest, found := strings.Cut(ref, "/")
	if !found || !idSegRe.MatchString(scope) {
		bad("FORM_INVALID")
	}
	out := map[string]any{"form": "endpoint"}
	name, path, hasPath := strings.Cut(rest, "/")
	name, port, hasPort := strings.Cut(name, ":")
	if hasPort {
		if !portNmRe.MatchString(port) || len(port) > 15 {
			bad("FORM_INVALID")
		}
		out["port"] = port
	}
	name, version, hasVersion := strings.Cut(name, "@")
	if hasVersion {
		if !verRe.MatchString(version) {
			bad("FORM_INVALID")
		}
		out["version"] = version
	}
	if !nameSegRe.MatchString(name) {
		bad("FORM_INVALID")
	}
	out["component"] = scope + "/" + name
	if hasPath {
		out["path"] = "/" + path
	}
	return out
}

func exec(op string, in map[string]any) (res any, reason string) {
	defer func() {
		if r := recover(); r != nil {
			if e, ok := r.(cfgErr); ok {
				reason = string(e)
				return
			}
			panic(r)
		}
	}()
	return run(op, in), ""
}

func main() {
	nbad, n := 0, 0
	files, _ := filepath.Glob(filepath.Join(os.Args[1], "*.json"))
	for _, f := range files {
		b, _ := os.ReadFile(f)
		var doc struct{ Cases []map[string]any }
		d := json.NewDecoder(bytes.NewReader(b))
		if err := d.Decode(&doc); err != nil {
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
				nbad++
				fmt.Printf("DISAGREE %s: want %v | go %v %s\n", c["id"], want, res, reason)
			}
		}
	}
	// informational: where Go's own helpers are broader than the protocol
	for _, v := range []string{"TRUE", "True", "t", "T"} {
		if b, err := strconv.ParseBool(v); err == nil {
			fmt.Printf("note: strconv.ParseBool(%q) = %v, the protocol rejects it\n", v, b)
		}
	}
	if _, err := strconv.ParseInt("+5", 10, 64); err == nil {
		fmt.Println("note: strconv.ParseInt accepts \"+5\", the protocol rejects it")
	}
	if u, err := url.Parse("HTTP://x:1"); err == nil {
		fmt.Printf("note: url.Parse lower-cases the scheme (%q), the protocol rejects upper case\n", u.Scheme)
	}
	fmt.Printf("config xcheck: %d cases, %d disagreements\n", n, nbad)
	if nbad > 0 {
		os.Exit(1)
	}
}
