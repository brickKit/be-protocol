package protocol

// Chapter 08: independent recomputation of the canonical-encoding, segment-eval and jwt-verify vectors.

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math/big"
	"regexp"
	"slices"
	"sort"
	"strings"
	"testing"
	"time"
	"unicode/utf8"
)

// ---------------------------------------------------------------- canonical encoding

var decRe = regexp.MustCompile(`^([+-]?)([0-9]*)(?:\.([0-9]*))?(?:[eE]([+-]?[0-9]+))?$`)

func refDecimal(s string) (string, bool) {
	m := decRe.FindStringSubmatch(s)
	if m == nil || m[2]+m[3] == "" {
		return "", false
	}
	digits := strings.TrimLeft(m[2]+m[3], "0")
	scale := len(m[3])
	if m[4] != "" {
		var e int
		fmt.Sscan(m[4], &e)
		scale -= e
	}
	if digits == "" {
		return "0", true
	}
	for scale > 0 && strings.HasSuffix(digits, "0") {
		digits, scale = digits[:len(digits)-1], scale-1
	}
	if len(digits) > 38 || scale > 18 {
		return "", false
	}
	if scale < 0 {
		digits += strings.Repeat("0", -scale)
		scale = 0
	}
	if len(digits) <= scale {
		digits = strings.Repeat("0", scale-len(digits)+1) + digits
	}
	out := digits[:len(digits)-scale]
	if scale > 0 {
		out += "." + digits[len(digits)-scale:]
	}
	if m[1] == "-" {
		out = "-" + out
	}
	return out, true
}

func refCanonical(buf *bytes.Buffer, v any) bool {
	switch x := v.(type) {
	case nil:
		return false
	case bool:
		fmt.Fprint(buf, x)
	case json.Number:
		n, ok := new(big.Int).SetString(x.String(), 10)
		if !ok || n.CmpAbs(new(big.Int).Lsh(big.NewInt(1), 53)) >= 0 {
			return false
		}
		buf.WriteString(n.String())
	case string:
		buf.WriteByte('"')
		for _, r := range x {
			switch {
			case r == '"':
				buf.WriteString(`\"`)
			case r == '\\':
				buf.WriteString(`\\`)
			case r == '\n':
				buf.WriteString(`\n`)
			case r == '\t':
				buf.WriteString(`\t`)
			case r == '\r':
				buf.WriteString(`\r`)
			case r == '\b':
				buf.WriteString(`\b`)
			case r == '\f':
				buf.WriteString(`\f`)
			case r < 0x20:
				fmt.Fprintf(buf, `\u%04x`, r)
			default:
				buf.WriteRune(r)
			}
		}
		buf.WriteByte('"')
	case []any:
		buf.WriteByte('[')
		for i, e := range x {
			if i > 0 {
				buf.WriteByte(',')
			}
			if !refCanonical(buf, e) {
				return false
			}
		}
		buf.WriteByte(']')
	case map[string]any:
		keys := make([]string, 0, len(x))
		for k := range x {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		buf.WriteByte('{')
		for i, k := range keys {
			if i > 0 {
				buf.WriteByte(',')
			}
			refCanonical(buf, k)
			buf.WriteByte(':')
			if !refCanonical(buf, x[k]) {
				return false
			}
		}
		buf.WriteByte('}')
	default:
		return false
	}
	return true
}

func decodeNumbers(raw json.RawMessage) any {
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	var v any
	_ = d.Decode(&v)
	if n, ok := v.(json.Number); ok && strings.ContainsAny(n.String(), ".eE") {
		return 1.5 // a float: refused
	}
	return fixFloats(v)
}

func fixFloats(v any) any {
	switch x := v.(type) {
	case json.Number:
		if strings.ContainsAny(x.String(), ".eE") {
			return 1.5
		}
	case []any:
		for i := range x {
			x[i] = fixFloats(x[i])
		}
	case map[string]any:
		for k := range x {
			x[k] = fixFloats(x[k])
		}
	}
	return v
}

func refDigest(recordType string, major int, canonical []byte) string {
	s := sha256.Sum256(append([]byte(fmt.Sprintf("%s.v%d\n", recordType, major)), canonical...))
	return "sha256:" + hex.EncodeToString(s[:])
}

func refSortedSet(items []any) []any {
	byBytes := map[string]any{}
	for _, it := range items {
		var b bytes.Buffer
		refCanonical(&b, it)
		byBytes[b.String()] = it
	}
	keys := make([]string, 0, len(byBytes))
	for k := range byBytes {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := []any{}
	for _, k := range keys {
		out = append(out, byBytes[k])
	}
	return out
}

func refInstant(s string) string {
	t, _ := time.Parse(time.RFC3339Nano, s)
	return t.UTC().Format("2006-01-02T15:04:05.000000Z")
}

func refSegment(seg map[string]any) map[string]any {
	delete(seg, "digest")
	for _, a := range seg["atoms"].(map[string]any) {
		atom := a.(map[string]any)
		switch atom["kind"] {
		case "in":
			atom["values"] = refSortedSet(atom["values"].([]any))
		case "tree":
			atom["items"] = refSortedSet(atom["items"].([]any))
		case "interval":
			for _, k := range []string{"lo", "hi"} {
				if v, ok := atom[k]; ok {
					atom[k], _ = refDecimal(v.(string))
				}
			}
		}
	}
	seg["read_fields"] = refSortedSet(seg["read_fields"].([]any))
	seg["write_fields"] = refSortedSet(seg["write_fields"].([]any))
	valid := seg["valid"].(map[string]any)
	for k, v := range valid {
		valid[k] = refInstant(v.(string))
	}
	return seg
}

func TestCanonicalVectors(t *testing.T) {
	for _, raw := range load(t, "canonical").Cases {
		var c struct {
			ID, Kind   string
			RecordType string `json:"record_type"`
			Major      int
			In         json.RawMessage
			Expect     struct{ Out, Canonical, Digest, Refused string }
		}
		_ = json.Unmarshal(raw, &c)
		var s string
		_ = json.Unmarshal(c.In, &s)
		got, refused := "", ""
		switch c.Kind {
		case "decimal":
			if d, ok := refDecimal(s); ok && !strings.Contains(s, "Inf") {
				got = d
			} else {
				refused = "decimal"
			}
		case "instant":
			if tm, err := time.Parse(time.RFC3339Nano, s); err == nil {
				got = tm.UTC().Format("2006-01-02T15:04:05.000000Z")
			} else {
				refused = "instant"
			}
		case "text":
			continue // NFC needs the Unicode tables; the SDK tests cover it
		case "json", "digest":
			var b bytes.Buffer
			if !refCanonical(&b, decodeNumbers(c.In)) {
				refused = "json"
			} else if c.Kind == "json" {
				got = b.String()
			} else {
				got = refDigest(c.RecordType, c.Major, b.Bytes())
			}
		case "segment":
			var b bytes.Buffer
			refCanonical(&b, refSegment(decodeNumbers(c.In).(map[string]any)))
			if b.String() != c.Expect.Canonical || refDigest("be.security.segment", 1, b.Bytes()) != c.Expect.Digest {
				t.Errorf("%s: canonical %s", c.ID, b.String())
			}
			continue
		}
		if got != c.Expect.Out || refused != c.Expect.Refused || !utf8.ValidString(got) {
			t.Errorf("%s: got %q refused %q, vector %q refused %q", c.ID, got, refused, c.Expect.Out, c.Expect.Refused)
		}
	}
}

// ---------------------------------------------------------------- jwt-verify

type jwk struct{ Kty, Kid, Alg, Crv, N, E, X, Y string }

func b64d(s string) []byte { b, _ := base64.RawURLEncoding.DecodeString(s); return b }

func refVerify(token string, keys map[string]jwk, issuer, audience string, now int64) string {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return "format"
	}
	var h struct{ Alg, Typ, Kid string }
	var c map[string]any
	if json.Unmarshal(b64d(parts[0]), &h) != nil || json.Unmarshal(b64d(parts[1]), &c) != nil {
		return "format"
	}
	if !slices.Contains([]string{"RS256", "ES256", "EdDSA"}, h.Alg) {
		return "alg"
	}
	if h.Typ != "at+jwt" {
		return "typ"
	}
	if h.Kid == "" {
		return "kid"
	}
	k, ok := keys[h.Kid]
	if !ok {
		return "kid_unknown"
	}
	if k.Alg != h.Alg {
		return "alg"
	}
	signed, sig := []byte(parts[0]+"."+parts[1]), b64d(parts[2])
	sum := sha256.Sum256(signed)
	valid := false
	switch h.Alg {
	case "RS256":
		pub := &rsa.PublicKey{N: new(big.Int).SetBytes(b64d(k.N)), E: int(new(big.Int).SetBytes(b64d(k.E)).Int64())}
		valid = rsa.VerifyPKCS1v15(pub, 5 /* crypto.SHA256 */, sum[:], sig) == nil
	case "ES256":
		pub := &ecdsa.PublicKey{Curve: elliptic.P256(), X: new(big.Int).SetBytes(b64d(k.X)), Y: new(big.Int).SetBytes(b64d(k.Y))}
		valid = len(sig) == 64 && ecdsa.Verify(pub, sum[:], new(big.Int).SetBytes(sig[:32]), new(big.Int).SetBytes(sig[32:]))
	case "EdDSA":
		valid = ed25519.Verify(ed25519.PublicKey(b64d(k.X)), signed, sig)
	}
	if !valid {
		return "signature"
	}
	if c["iss"] != issuer {
		return "iss"
	}
	audOK := c["aud"] == audience
	if list, ok := c["aud"].([]any); ok {
		audOK = slices.Contains(list, any(audience))
	}
	if !audOK {
		return "aud"
	}
	num := func(k string) (int64, bool) { f, ok := c[k].(float64); return int64(f), ok }
	if exp, ok := num("exp"); !ok || exp <= now-60 {
		return "exp"
	}
	if nbf, ok := num("nbf"); ok && nbf > now+60 {
		return "nbf"
	}
	if iat, ok := num("iat"); ok && iat > now+60 {
		return "iat"
	}
	if sub, _ := c["sub"].(string); !regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`).MatchString(sub) {
		return "sub"
	}
	return ""
}

func TestJWTVerifyVectors(t *testing.T) {
	cs := load(t, "jwt-verify").Cases
	var fixture struct {
		JWKS             struct{ Keys []jwk }
		Issuer, Audience string
		Now              int64
	}
	_ = json.Unmarshal(cs[0], &fixture)
	keys := map[string]jwk{}
	for _, k := range fixture.JWKS.Keys {
		keys[k.Kid] = k
	}
	for _, raw := range cs[1:] {
		var c struct {
			ID, Token string
			Expect    struct {
				Valid   bool
				Problem string
			}
		}
		_ = json.Unmarshal(raw, &c)
		if got := refVerify(c.Token, keys, fixture.Issuer, fixture.Audience, fixture.Now); got != c.Expect.Problem || c.Expect.Valid != (got == "") {
			t.Errorf("%s: recomputed %q, vector %q", c.ID, got, c.Expect.Problem)
		}
	}
}

// ---------------------------------------------------------------- segment-eval

func TestSegmentEvalVectorsAreConsistent(t *testing.T) {
	cs := load(t, "segment-eval").Cases
	var fixture struct {
		Records []struct{ ID string }
	}
	_ = json.Unmarshal(cs[0], &fixture)
	for _, raw := range cs[1:] {
		var c struct {
			ID, Kind string
			Expect   struct {
				Records map[string]struct {
					Visible, Action string
					Fields          []string
				}
				List struct {
					IDs    []string `json:"ids"`
					Fields map[string][]string
				}
			}
		}
		_ = json.Unmarshal(raw, &c)
		if c.Kind != "evaluate" {
			continue
		}
		for id, r := range c.Expect.Records {
			if r.Visible != "true" && len(r.Fields) > 0 {
				t.Errorf("%s/%s: fields on an invisible record", c.ID, id)
			}
			if r.Visible == "false" && r.Action == "true" {
				t.Errorf("%s/%s: an action allowed on an invisible record", c.ID, id)
			}
			if slices.Contains(r.Fields, "note") {
				t.Errorf("%s/%s: a secret field is output", c.ID, id)
			}
		}
		for _, id := range c.Expect.List.IDs {
			if c.Expect.Records[id].Visible != "true" {
				t.Errorf("%s: %s listed but not visible", c.ID, id)
			}
		}
	}
	if len(fixture.Records) < 9 {
		t.Fatal("fixture missing")
	}
}
