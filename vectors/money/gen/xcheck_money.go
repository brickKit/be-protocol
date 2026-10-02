//go:build ignore

// xcheck_money recomputes every case in vectors/money/*.json with Go's
// math/big.Rat, independently of gen_money.py (no shared code, no shared
// tables except the ISO XML, whose sample is also checked against a table
// typed in by hand below). It prints every disagreement and exits 1 if any.
//
//	docker run --rm -v "$PWD":/v -w /v golang:1.22-alpine go run money/gen/xcheck_money.go money
package main

import (
	"encoding/json"
	"encoding/xml"
	"fmt"
	"math/big"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"sort"
	"strings"
)

type merr string

func (e merr) Error() string { return string(e) }

var (
	syntaxRe = regexp.MustCompile(`^-?[0-9]+(\.[0-9]+)?$`)
	ccyRe    = regexp.MustCompile(`^[A-Z]{3}$`)
	kinds    = map[string][2]int{"amount": {19, 4}, "price": {19, 6}, "cost": {19, 6}, "quantity": {19, 6},
		"rate": {19, 10}, "ratio": {9, 6}, "factor": {24, 12}}
	iso = map[string]int{}
)

// typed by hand from general knowledge of ISO 4217, to catch a bad XML read
var handMinor = map[string]int{"CNY": 2, "USD": 2, "EUR": 2, "GBP": 2, "HKD": 2, "MOP": 2, "TWD": 2, "JPY": 0,
	"KRW": 0, "VND": 0, "IDR": 2, "INR": 2, "SGD": 2, "CHF": 2, "AUD": 2, "CAD": 2, "RUB": 2, "BRL": 2,
	"KWD": 3, "BHD": 3, "OMR": 3, "JOD": 3, "TND": 3, "LYD": 3, "IQD": 3, "CLP": 0, "CLF": 4, "UYW": 4,
	"ISK": 0, "HUF": 2, "PYG": 0, "UGX": 0, "XAF": 0, "XOF": 0}

func loadISO(path string) {
	type entry struct {
		Ccy string `xml:"Ccy"`
		Mnr string `xml:"CcyMnrUnts"`
	}
	var doc struct {
		Entries []entry `xml:"CcyTbl>CcyNtry"`
	}
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := xml.Unmarshal(b, &doc); err != nil {
		panic(err)
	}
	for _, e := range doc.Entries {
		var n int
		if e.Ccy == "" {
			continue
		}
		if _, err := fmt.Sscanf(e.Mnr, "%d", &n); err != nil {
			continue
		}
		iso[e.Ccy] = n
	}
}

func parse(v any) *big.Rat {
	s, ok := v.(string)
	if !ok || !syntaxRe.MatchString(s) {
		panic(merr("DECIMAL_SYNTAX"))
	}
	r, ok := new(big.Rat).SetString(s)
	if !ok {
		panic(merr("DECIMAL_SYNTAX"))
	}
	return r
}

func pow10(n int) *big.Int { return new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(n)), nil) }

func scaleOf(r *big.Rat) int {
	for n := 0; n < 500; n++ {
		x := new(big.Rat).Mul(r, new(big.Rat).SetInt(pow10(n)))
		if x.IsInt() {
			return n
		}
	}
	panic("non-terminating")
}

func intDigits(r *big.Rat) int {
	a := new(big.Rat).Abs(r)
	q := new(big.Int).Quo(a.Num(), a.Denom())
	if q.Sign() == 0 {
		return 0
	}
	return len(q.String())
}

func capacity(r *big.Rat, kind string) {
	k, ok := kinds[kind]
	if !ok {
		panic(merr("KIND_UNKNOWN"))
	}
	if intDigits(r) > k[0]-k[1] {
		panic(merr("DECIMAL_OVERFLOW"))
	}
	if scaleOf(r) > k[1] {
		panic(merr("DECIMAL_SCALE"))
	}
}

func minorOf(v any) int {
	s, _ := v.(string)
	if !ccyRe.MatchString(s) {
		panic(merr("CURRENCY_INVALID"))
	}
	m, ok := iso[s]
	if !ok {
		panic(merr("CURRENCY_UNKNOWN"))
	}
	return m
}

// format uses big.Rat.FloatString, which rounds half away from zero; the
// value is always exact at `scale` here, so no rounding happens.
func format(r *big.Rat, scale int) string {
	s := r.FloatString(scale)
	if strings.Trim(s, "-0.") == "" {
		s = strings.TrimPrefix(s, "-")
	}
	return s
}

func modeOf(in map[string]any) string {
	m, ok := in["mode"]
	if !ok {
		return "HALF_AWAY_FROM_ZERO"
	}
	s, _ := m.(string)
	if s != "HALF_AWAY_FROM_ZERO" && s != "HALF_EVEN" {
		panic(merr("MODE_UNKNOWN"))
	}
	return s
}

// roundStep rounds r to a multiple of step using integer division on
// numerator and denominator (different from the Python reference, which
// compares the remainder against one half).
func roundStep(r, step *big.Rat, mode string) *big.Rat {
	q := new(big.Rat).Quo(r, step)
	neg := q.Sign() < 0
	q.Abs(q)
	num, den := q.Num(), q.Denom()
	fl, rem := new(big.Int).QuoRem(num, den, new(big.Int))
	twice := new(big.Int).Mul(rem, big.NewInt(2))
	switch c := twice.Cmp(den); {
	case c > 0:
		fl.Add(fl, big.NewInt(1))
	case c == 0:
		if mode == "HALF_AWAY_FROM_ZERO" || fl.Bit(0) == 1 {
			fl.Add(fl, big.NewInt(1))
		}
	}
	if neg {
		fl.Neg(fl)
	}
	return new(big.Rat).Mul(new(big.Rat).SetInt(fl), step)
}

func unit(scale int) *big.Rat { return new(big.Rat).SetFrac(big.NewInt(1), pow10(scale)) }

func allocate(total *big.Rat, weights []any, scale int) []*big.Rat {
	if len(weights) == 0 {
		panic(merr("ALLOCATION_INVALID"))
	}
	ws := make([]*big.Rat, len(weights))
	sum := new(big.Rat)
	for i, w := range weights {
		ws[i] = parse(w)
		if ws[i].Sign() < 0 {
			panic(merr("ALLOCATION_INVALID"))
		}
		sum.Add(sum, ws[i])
	}
	if sum.Sign() == 0 {
		panic(merr("ALLOCATION_INVALID"))
	}
	if scaleOf(total) > scale {
		panic(merr("DECIMAL_SCALE"))
	}
	sign := total.Sign()
	abs := new(big.Rat).Abs(total)
	units := new(big.Rat).Mul(abs, new(big.Rat).SetInt(pow10(scale))) // integer
	type share struct {
		i    int
		fl   *big.Int
		remN *big.Rat
	}
	shares := make([]share, len(ws))
	given := new(big.Int)
	for i, w := range ws {
		ex := new(big.Rat).Mul(units, w)
		ex.Quo(ex, sum)
		fl := new(big.Int).Quo(ex.Num(), ex.Denom())
		rem := new(big.Rat).Sub(ex, new(big.Rat).SetInt(fl))
		shares[i] = share{i, fl, rem}
		given.Add(given, fl)
	}
	left := new(big.Int).Sub(units.Num(), given).Int64()
	order := make([]share, len(shares))
	copy(order, shares)
	sort.SliceStable(order, func(a, b int) bool { return order[a].remN.Cmp(order[b].remN) > 0 })
	for k := int64(0); k < left; k++ {
		shares[order[k].i].fl.Add(shares[order[k].i].fl, big.NewInt(1))
	}
	out := make([]*big.Rat, len(ws))
	for i, s := range shares {
		v := new(big.Rat).Mul(new(big.Rat).SetInt(s.fl), unit(scale))
		if sign < 0 {
			v.Neg(v)
		}
		out[i] = v
	}
	return out
}

func ratio01(v any) *big.Rat {
	r := parse(v)
	capacity(r, "ratio")
	if r.Sign() < 0 || r.Cmp(big.NewRat(1, 1)) > 0 {
		panic(merr("RATIO_INVALID"))
	}
	return r
}

func amountIn(a any) (*big.Rat, int) {
	m := a.(map[string]any)
	mi := minorOf(m["currency"])
	r := parse(m["value"])
	capacity(r, "amount")
	if scaleOf(r) > mi {
		panic(merr("DECIMAL_SCALE"))
	}
	return r, mi
}

func normal(r *big.Rat) string { return format(r, scaleOf(r)) }

func run(op string, in map[string]any) (out any) {
	switch op {
	case "column":
		k := in["kind"].(string)
		if k == "currency" {
			return map[string]any{"sql": "CHAR(3)", "precision": nil, "scale": nil, "integer_digits": nil}
		}
		p, ok := kinds[k]
		if !ok {
			panic(merr("KIND_UNKNOWN"))
		}
		return map[string]any{"sql": fmt.Sprintf("NUMERIC(%d,%d)", p[0], p[1]), "precision": float64(p[0]),
			"scale": float64(p[1]), "integer_digits": float64(p[0] - p[1])}
	case "minor_units":
		return map[string]any{"minor_units": float64(minorOf(in["currency"]))}
	case "parse":
		k := in["kind"].(string)
		if _, ok := kinds[k]; !ok && k != "decimal" {
			panic(merr("KIND_UNKNOWN"))
		}
		r := parse(in["value"])
		if k != "decimal" {
			capacity(r, k)
		}
		return map[string]any{"value": normal(r)}
	case "format":
		r := parse(in["value"])
		m := minorOf(in["currency"])
		capacity(r, "amount")
		if scaleOf(r) > m {
			panic(merr("DECIMAL_SCALE"))
		}
		return map[string]any{"value": format(r, m)}
	case "round":
		r := parse(in["value"])
		mode := modeOf(in)
		var sc int
		if c, ok := in["currency"]; ok {
			sc = minorOf(c)
		} else {
			sc = int(in["scale"].(float64))
		}
		return map[string]any{"value": format(roundStep(r, unit(sc), mode), sc)}
	case "round_cash":
		r := parse(in["value"])
		m := minorOf(in["currency"])
		mode := modeOf(in)
		inc := parse(in["increment"])
		if inc.Sign() <= 0 || scaleOf(inc) > m {
			panic(merr("ROUNDING_INVALID"))
		}
		return map[string]any{"value": format(roundStep(r, inc, mode), m)}
	case "round_qty":
		r := parse(in["value"])
		mode := modeOf(in)
		st := parse(in["rounding"])
		if st.Sign() <= 0 {
			panic(merr("ROUNDING_INVALID"))
		}
		return map[string]any{"value": format(roundStep(r, st, mode), scaleOf(st))}
	case "allocate":
		m := minorOf(in["currency"])
		parts := allocate(parse(in["total"]), in["weights"].([]any), m)
		ss := make([]any, len(parts))
		for i, p := range parts {
			ss[i] = format(p, m)
		}
		return map[string]any{"parts": ss}
	case "tax_line", "tax_document":
		m := minorOf(in["currency"])
		mode := modeOf(in)
		rate := ratio01(in["rate"])
		lines := in["lines"].([]any)
		nets := make([]*big.Rat, len(lines))
		sum := new(big.Rat)
		for i, l := range lines {
			nets[i], _ = amountIn(map[string]any{"value": l, "currency": in["currency"]})
			sum.Add(sum, nets[i])
		}
		var taxes []*big.Rat
		total := new(big.Rat)
		if op == "tax_line" {
			for _, n := range nets {
				t := roundStep(new(big.Rat).Mul(n, rate), unit(m), mode)
				taxes = append(taxes, t)
				total.Add(total, t)
			}
		} else {
			total = roundStep(new(big.Rat).Mul(sum, rate), unit(m), mode)
			taxes = allocate(total, lines, m)
		}
		ts := make([]any, len(taxes))
		for i, t := range taxes {
			ts[i] = format(t, m)
		}
		return map[string]any{"line_taxes": ts, "total": format(total, m)}
	case "add", "sub":
		a, m := amountIn(in["a"])
		b, _ := amountIn(in["b"])
		ca := in["a"].(map[string]any)["currency"]
		if ca != in["b"].(map[string]any)["currency"] {
			panic(merr("CURRENCY_MISMATCH"))
		}
		v := new(big.Rat)
		if op == "add" {
			v.Add(a, b)
		} else {
			v.Sub(a, b)
		}
		capacity(v, "amount")
		return map[string]any{"value": format(v, m), "currency": ca}
	case "convert":
		a, _ := amountIn(in["amount"])
		m := minorOf(in["to"])
		mode := modeOf(in)
		rate := parse(in["rate"])
		capacity(rate, "rate")
		if rate.Sign() <= 0 || (in["amount"].(map[string]any)["currency"] == in["to"] && rate.Cmp(big.NewRat(1, 1)) != 0) {
			panic(merr("RATE_INVALID"))
		}
		v := roundStep(new(big.Rat).Mul(a, rate), unit(m), mode)
		capacity(v, "amount")
		return map[string]any{"value": format(v, m), "currency": in["to"]}
	case "line_amount":
		m := minorOf(in["currency"])
		mode := modeOf(in)
		q := parse(in["quantity"])
		capacity(q, "quantity")
		p := parse(in["price"])
		capacity(p, "price")
		d := big.NewRat(0, 1)
		if dv, ok := in["discount"]; ok {
			d = ratio01(dv)
		}
		x := new(big.Rat).Mul(q, p)
		x.Mul(x, new(big.Rat).Sub(big.NewRat(1, 1), d))
		v := roundStep(x, unit(m), mode)
		capacity(v, "amount")
		return map[string]any{"value": format(v, m), "currency": in["currency"]}
	}
	panic("unknown op " + op)
}

func exec(op string, in map[string]any) (res any, reason string) {
	defer func() {
		if r := recover(); r != nil {
			if e, ok := r.(merr); ok {
				reason = string(e)
				return
			}
			panic(r)
		}
	}()
	return run(op, in), ""
}

func main() {
	dir := os.Args[1]
	loadISO(filepath.Join(dir, "gen", "iso4217-list-one.xml"))
	bad, n := 0, 0
	for code, m := range handMinor {
		if iso[code] != m {
			fmt.Printf("ISO TABLE: %s xml=%d hand=%d\n", code, iso[code], m)
			bad++
		}
	}
	files, _ := filepath.Glob(filepath.Join(dir, "*.json"))
	for _, f := range files {
		b, _ := os.ReadFile(f)
		var doc map[string]any
		if err := json.Unmarshal(b, &doc); err != nil {
			panic(err)
		}
		if _, ok := doc["cases"]; !ok {
			// iso4217.json: compare the whole table with the XML read here
			mu := doc["minor_units"].(map[string]any)
			if len(mu) != len(iso) {
				fmt.Printf("ISO TABLE size %d vs %d\n", len(mu), len(iso))
				bad++
			}
			for k, v := range mu {
				if int(v.(float64)) != iso[k] {
					fmt.Printf("ISO TABLE %s\n", k)
					bad++
				}
			}
			continue
		}
		for _, c := range doc["cases"].([]any) {
			cs := c.(map[string]any)
			n++
			res, reason := exec(cs["op"].(string), cs["input"].(map[string]any))
			if e, ok := cs["expected_error"]; ok {
				want := e.(map[string]any)["reason"].(string)
				if reason != want {
					fmt.Printf("DISAGREE %s: want error %s, go got %v %s\n", cs["id"], want, res, reason)
					bad++
				}
				continue
			}
			if reason != "" || !reflect.DeepEqual(res, cs["expected"]) {
				fmt.Printf("DISAGREE %s: want %v, go got %v %s\n", cs["id"], cs["expected"], res, reason)
				bad++
			}
		}
	}
	fmt.Printf("money xcheck: %d cases, %d disagreements\n", n, bad)
	if bad > 0 {
		os.Exit(1)
	}
}
