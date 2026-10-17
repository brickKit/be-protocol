package protocol

// Chapter 05: the database vectors are tables chosen by hand rather than computed, so the checks here hold them to the
// rest of the protocol instead of recomputing them: every reason exists in the catalog, every lint rule is defined,
// and the shared migration files have the names the lint requires.

import (
	"encoding/json"
	"io/fs"
	"regexp"
	"strings"
	"testing"
)

func catalogReasons(t *testing.T) map[string]bool {
	reasons := map[string]bool{}
	for _, raw := range load(t, "errors").Cases {
		var c struct{ Kind, Reason string }
		_ = json.Unmarshal(raw, &c)
		if c.Kind == "reason" {
			reasons[c.Reason] = true
		}
	}
	return reasons
}

func TestDBErrorsVectors(t *testing.T) {
	reasons := catalogReasons(t)
	sqlstate := regexp.MustCompile(`^[0-9A-Z]{5}$`)
	for _, raw := range load(t, "db-errors").Cases {
		var c struct {
			ID, Sqlstate, Reason string
			Retried              bool
		}
		_ = json.Unmarshal(raw, &c)
		if !reasons[c.Reason] {
			t.Errorf("%s: reason %s is not in the catalog", c.ID, c.Reason)
		}
		if c.Sqlstate != "connect" && !sqlstate.MatchString(c.Sqlstate) {
			t.Errorf("%s: sqlstate %q", c.ID, c.Sqlstate)
		}
		if c.Retried != (c.Sqlstate == "40001" || c.Sqlstate == "40P01") {
			t.Errorf("%s: only 40001 and 40P01 are retried (P5.7)", c.ID)
		}
	}
}

func TestMigrationLintVectors(t *testing.T) {
	v := load(t, "migration-lint")
	defined := map[string]bool{}
	for _, m := range regexp.MustCompile(`([A-Z_]+): `).FindAllStringSubmatch(v.Description[strings.Index(v.Description, "规则："):], -1) {
		defined[m[1]] = true
	}
	for _, raw := range v.Cases {
		var c struct {
			ID      string
			Files   map[string]string
			Refused []struct{ File, Rule string }
		}
		_ = json.Unmarshal(raw, &c)
		for _, r := range c.Refused {
			if !defined[r.Rule] {
				t.Errorf("%s: rule %s is not defined in the description", c.ID, r.Rule)
			}
			if _, ok := c.Files[r.File]; !ok {
				t.Errorf("%s: refused file %s is not in the case", c.ID, r.File)
			}
		}
	}
}

func TestSharedMigrationFiles(t *testing.T) {
	entries, err := fs.ReadDir(Migrations, "migrations")
	if err != nil || len(entries) == 0 {
		t.Fatalf("no shared migrations: %v", err)
	}
	name := regexp.MustCompile(`^[0-9]+_[a-z0-9_]+\.up\.sql$`)
	for _, e := range entries {
		if !name.MatchString(e.Name()) {
			t.Errorf("%s: not <version>_<title>.up.sql", e.Name())
		}
		body, _ := fs.ReadFile(Migrations, "migrations/"+e.Name())
		if !strings.Contains(string(body), "be_") {
			t.Errorf("%s: SDK tables are prefixed be_", e.Name())
		}
	}
}

func TestCronSlotVectorsAreWellFormed(t *testing.T) {
	for _, raw := range load(t, "cron-slots").Cases {
		var c struct {
			ID, Kind, Cron, TZ string
		}
		_ = json.Unmarshal(raw, &c)
		if (c.Kind != "slots" && c.Kind != "materialize") || len(strings.Fields(c.Cron)) != 5 || c.TZ == "" {
			t.Errorf("%s: kind, a 5-field cron and a time zone are required", c.ID)
		}
	}
}
