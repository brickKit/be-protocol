package protocol

import (
	"bytes"
	"encoding/json"
	"io/fs"
	"strings"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

// securitySchemas compiles every schemas/security/*.schema.json (generated from the field tables, D76).
func securitySchemas(t *testing.T) map[string]*jsonschema.Schema {
	t.Helper()
	c := jsonschema.NewCompiler()
	names, err := fs.Glob(Schemas, "schemas/security/*.schema.json")
	if err != nil || len(names) == 0 {
		t.Fatalf("no security schemas: %v", err)
	}
	out := map[string]*jsonschema.Schema{}
	for _, n := range names {
		raw, _ := fs.ReadFile(Schemas, n)
		doc, err := jsonschema.UnmarshalJSON(bytes.NewReader(raw))
		if err != nil {
			t.Fatal(err)
		}
		if err := c.AddResource(n, doc); err != nil {
			t.Fatal(err)
		}
		s, err := c.Compile(n)
		if err != nil {
			t.Fatalf("%s: %v", n, err)
		}
		out[strings.TrimSuffix(strings.TrimPrefix(n, "schemas/security/"), ".schema.json")] = s
	}
	return out
}

func TestSecurityRecordVectors(t *testing.T) {
	schemas := securitySchemas(t)
	for _, raw := range load(t, "security-records").Cases {
		var c struct {
			ID         string
			RecordType string `json:"record_type"`
			Record     json.RawMessage
			Valid      bool
			Canonical  string
			Digest     string
		}
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		s := schemas[c.RecordType]
		if s == nil {
			t.Fatalf("%s: no schema for %s", c.ID, c.RecordType)
		}
		inst, err := jsonschema.UnmarshalJSON(bytes.NewReader(c.Record))
		if err != nil {
			t.Fatal(err)
		}
		if err := s.Validate(inst); (err == nil) != c.Valid {
			t.Errorf("%s: the schema says %v, the vector says valid=%v", c.ID, err, c.Valid)
		}
		if !c.Valid {
			continue
		}
		d := json.NewDecoder(bytes.NewReader(c.Record))
		d.UseNumber()
		var v any
		_ = d.Decode(&v)
		var buf bytes.Buffer
		if !refCanonical(&buf, v) || buf.String() != c.Canonical || refDigest(c.RecordType, 1, buf.Bytes()) != c.Digest {
			t.Errorf("%s: canonical bytes or digest differ", c.ID)
		}
	}
}
