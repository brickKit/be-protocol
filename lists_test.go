package protocol

// Chapter 09: independent recomputation of the search, list-pages and projection-apply vectors.

import (
	"bufio"
	"encoding/json"
	"math/big"
	"reflect"
	"sort"
	"strconv"
	"strings"
	"testing"
	"unicode"

	"golang.org/x/text/unicode/norm"
)

func pinyinTable(t *testing.T) map[rune]string {
	f, err := Data.Open("data/pinyin.tsv")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	out := map[rune]string{}
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		if strings.HasPrefix(line, "#") {
			continue
		}
		cp, reading, _ := strings.Cut(line, "\t")
		n, _ := strconv.ParseInt(cp, 16, 32)
		out[rune(n)] = reading
	}
	return out
}

func refFold(s string) string {
	var b strings.Builder
	for _, r := range strings.ToLower(norm.NFKC.String(s)) {
		if !unicode.IsControl(r) && !unicode.Is(unicode.Cf, r) {
			b.WriteRune(r)
		}
	}
	return b.String()
}

func TestSearchVectors(t *testing.T) {
	py := pinyinTable(t)
	text := func(values []string) string {
		var parts []string
		for _, v := range values {
			f := refFold(v)
			var full, ini strings.Builder
			for _, r := range f {
				if p, ok := py[r]; ok {
					full.WriteString(p)
					ini.WriteByte(p[0])
				} else {
					full.WriteRune(r)
					ini.WriteRune(r)
				}
			}
			parts = append(parts, f, full.String(), ini.String())
		}
		return strings.Join(parts, "\x1f")
	}
	for _, raw := range load(t, "search").Cases {
		var c struct {
			ID, Kind, Q string
			Values      []string
			Expect      json.RawMessage
		}
		_ = json.Unmarshal(raw, &c)
		var got any
		switch c.Kind {
		case "text":
			got = text(c.Values)
		case "query":
			got = strings.TrimSpace(refFold(c.Q))
		case "match":
			q, ok := strings.TrimSpace(refFold(c.Q)), false
			for _, part := range strings.Split(text(c.Values), "\x1f") {
				ok = ok || q == "" || strings.Contains(part, q)
			}
			got = ok
		}
		want, _ := json.Marshal(got)
		if string(want) != string(c.Expect) {
			t.Errorf("%s: recomputed %s, vector %s", c.ID, want, c.Expect)
		}
	}
}

func TestListPagesVectors(t *testing.T) {
	cs := load(t, "list-pages").Cases
	var fx struct{ Rows []map[string]string }
	_ = json.Unmarshal(cs[0], &fx)
	for _, raw := range cs[1:] {
		var c struct {
			ID, Kind string
			Sort     []struct{ Field, Dir string }
			PageSize int `json:"page_size"`
			Expect   json.RawMessage
		}
		_ = json.Unmarshal(raw, &c)
		if c.Kind == "refused" {
			if c.PageSize > 0 && c.PageSize <= 200 {
				t.Errorf("%s: page size %d is allowed", c.ID, c.PageSize)
			}
			continue
		}
		rows := append([]map[string]string(nil), fx.Rows...)
		less := func(a, b map[string]string) int {
			for _, o := range append(c.Sort, struct{ Field, Dir string }{"id", "asc"}) {
				var cmp int
				if o.Field == "amount" {
					x, _ := new(big.Rat).SetString(a[o.Field])
					y, _ := new(big.Rat).SetString(b[o.Field])
					cmp = x.Cmp(y)
				} else {
					cmp = strings.Compare(a[o.Field], b[o.Field])
				}
				if o.Dir == "desc" {
					cmp = -cmp
				}
				if cmp != 0 {
					return cmp
				}
			}
			return 0
		}
		sort.SliceStable(rows, func(i, j int) bool { return less(rows[i], rows[j]) < 0 })
		var pages [][]string
		for i := 0; i < len(rows); i += c.PageSize {
			var page []string
			for _, r := range rows[i:min(i+c.PageSize, len(rows))] {
				page = append(page, r["id"])
			}
			pages = append(pages, page)
		}
		var want [][]string
		_ = json.Unmarshal(c.Expect, &want)
		if !reflect.DeepEqual(pages, want) {
			t.Errorf("%s: recomputed %v", c.ID, pages)
		}
	}
}

func TestProjectionApplyVectors(t *testing.T) {
	for _, raw := range load(t, "projection-apply").Cases {
		var c struct {
			ID      string
			Current *struct {
				State       string
				Version     int64
				NeedVersion int64 `json:"need_version"`
				Old         bool
			}
			Input struct {
				Kind    string
				Version int64
			}
			Expect struct {
				State       string
				Version     int64
				NeedVersion int64 `json:"need_version"`
				Action      string
			}
		}
		_ = json.Unmarshal(raw, &c)
		k, v := c.Input.Kind, c.Input.Version
		type res struct {
			st     string
			ver    int64
			need   int64
			action string
		}
		var r res
		cur := c.Current
		switch {
		case cur == nil:
			r = map[string]res{"full": {"complete", v, 0, "write"}, "partial": {"incomplete", v, v, "write_and_fetch"},
				"delete": {"tombstone", v, 0, "write"}}[k]
		case cur.Old && k == "partial":
			r = res{"incomplete", v, v, "write_and_fetch"}
		case cur.Old:
			r = res{map[string]string{"full": "complete", "delete": "tombstone"}[k], v, 0, "overwrite"}
		case cur.State == "tombstone" && v <= cur.Version:
			r = res{"tombstone", cur.Version, 0, "ignore"}
		case cur.State == "tombstone":
			r = map[string]res{"full": {"complete", v, 0, "overwrite"}, "partial": {"incomplete", v, v, "write_and_fetch"},
				"delete": {"tombstone", v, 0, "write"}}[k]
		case k == "full" && cur.State == "complete" && v > cur.Version, k == "full" && cur.State == "incomplete" && v >= cur.NeedVersion:
			r = res{"complete", v, 0, "overwrite"}
		case k == "partial" && v > cur.Version:
			r = res{"incomplete", v, v, "merge_and_fetch"}
		case k == "delete" && v >= cur.Version:
			r = res{"tombstone", v, 0, "write"}
		default:
			r = res{cur.State, cur.Version, cur.NeedVersion, "ignore"}
		}
		if r.st != c.Expect.State || r.ver != c.Expect.Version || r.need != c.Expect.NeedVersion || r.action != c.Expect.Action {
			t.Errorf("%s: recomputed %+v, vector %+v", c.ID, r, c.Expect)
		}
	}
}
