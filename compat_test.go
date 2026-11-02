package protocol

import (
	"os"
	"strings"
	"testing"
)

// TestCompatRowsNameTheFormalDocuments: every protocol version in COMPAT.md section 1 says where the assembly
// project's formal documents took the change, or why they need nothing ("无：..."). Without it, six clause changes
// reached the documents only when step 14 of the representative deployment experiment went looking for them.
func TestCompatRowsNameTheFormalDocuments(t *testing.T) {
	b, err := os.ReadFile("COMPAT.md")
	if err != nil {
		t.Fatal(err)
	}
	section := strings.SplitN(strings.SplitN(string(b), "## 1. ", 2)[1], "\n## ", 2)[0]
	var header []string
	rows := 0
	for _, line := range strings.Split(section, "\n") {
		if !strings.HasPrefix(line, "|") || strings.HasPrefix(line, "| ---") {
			continue
		}
		cells := strings.Split(strings.Trim(line, "|"), "|")
		for i := range cells {
			cells[i] = strings.TrimSpace(cells[i])
		}
		if header == nil {
			header = cells
			if header[len(header)-1] != "装配项目的正式文档" {
				t.Fatalf("section 1's last column is %q, want 装配项目的正式文档", header[len(header)-1])
			}
			continue
		}
		rows++
		if len(cells) != len(header) {
			t.Errorf("%s: %d cells, want %d", cells[0], len(cells), len(header))
			continue
		}
		if last := cells[len(cells)-1]; last == "" {
			t.Errorf("%s: name the formal documents that took the change, or write 无：<why>", cells[0])
		}
	}
	if rows == 0 {
		t.Fatal("section 1 has no version rows")
	}
}
