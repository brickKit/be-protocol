package protocol

import (
	"encoding/json"
	"io/fs"
	"os"
	"regexp"
	"strings"
	"testing"
)

// specFS is the repository tree; the tests run from the module root.
var specFS = os.DirFS(".")

func TestEveryRuleBelongsToExactlyOneCapability(t *testing.T) {
	var doc struct {
		Protocol     string
		Capabilities []struct {
			ID, Title, Owner string
			Rules            []string
		}
	}
	if err := json.Unmarshal(Capabilities, &doc); err != nil {
		t.Fatal(err)
	}
	if doc.Protocol != Version {
		t.Errorf("capabilities.json is for %s, the tree is %s", doc.Protocol, Version)
	}
	rows := regexp.MustCompile(`(?m)^\| (P[0-9]+\.[0-9]+) \|`)
	spec := map[string]bool{}
	files, _ := fs.Glob(specFS, "spec/*.md")
	for _, f := range files {
		b, _ := fs.ReadFile(specFS, f)
		for _, m := range rows.FindAllStringSubmatch(string(b), -1) {
			spec[m[1]] = true
		}
	}
	if len(spec) == 0 {
		t.Fatal("no rules found in spec/")
	}
	owner := map[string]bool{}
	ids := map[string]bool{}
	id := regexp.MustCompile(`^[a-z][a-z0-9-]*$`)
	for _, c := range doc.Capabilities {
		if !id.MatchString(c.ID) || ids[c.ID] || strings.TrimSpace(c.Title) == "" {
			t.Errorf("capability %q: the ID must be unique lowercase-kebab and the title set", c.ID)
		}
		ids[c.ID] = true
		if c.Owner != "sdk" && c.Owner != "component" && c.Owner != "assembly" {
			t.Errorf("%s: owner %q", c.ID, c.Owner)
		}
		for _, r := range c.Rules {
			if !spec[r] {
				t.Errorf("%s: %s is not a rule of spec/", c.ID, r)
			}
			if owner[r] {
				t.Errorf("%s: %s belongs to another capability too", c.ID, r)
			}
			owner[r] = true
		}
	}
	for r := range spec {
		if !owner[r] {
			t.Errorf("%s belongs to no capability", r)
		}
	}
}
