package protocol

import (
	"encoding/json"
	"math/big"
	"regexp"
	"strings"
	"testing"
	"time"
	_ "time/tzdata"
)

// The money reference uses big.Rat: exact, and unrelated to the generator's decimal module.

var refDecimalRe = regexp.MustCompile(`^-?(0|[1-9][0-9]*)(\.[0-9]+)?$`)

func refRat(s string) *big.Rat {
	r, ok := new(big.Rat).SetString(s)
	if !ok {
		panic("not a decimal: " + s)
	}
	return r
}

func pow10(n int) *big.Int { return new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(n)), nil) }

// refUnits is r in units of 10^-scale, rounded by mode.
func refUnits(r *big.Rat, scale int, mode string) *big.Int {
	x := new(big.Rat).Mul(r, new(big.Rat).SetInt(pow10(scale)))
	return refRoundRat(x, mode)
}

// refRoundRat rounds x to an integer: half away from zero, or half to even.
func refRoundRat(x *big.Rat, mode string) *big.Int {
	neg := x.Sign() < 0
	a := new(big.Rat).Abs(x)
	q, m := new(big.Int).QuoRem(a.Num(), a.Denom(), new(big.Int))
	twice := new(big.Int).Mul(m, big.NewInt(2))
	switch c := twice.Cmp(a.Denom()); {
	case c > 0, c == 0 && mode == "half_away_from_zero", c == 0 && q.Bit(0) == 1:
		q.Add(q, big.NewInt(1))
	}
	if neg {
		q.Neg(q)
	}
	return q
}

func refFormat(units *big.Int, scale int) string {
	neg := units.Sign() < 0
	digits := new(big.Int).Abs(units).String()
	if scale > 0 {
		for len(digits) <= scale {
			digits = "0" + digits
		}
		digits = digits[:len(digits)-scale] + "." + digits[len(digits)-scale:]
	}
	if neg {
		return "-" + digits
	}
	return digits
}

func refParseAmount(s string, scale int) (string, bool) {
	if !refDecimalRe.MatchString(s) || len(strings.NewReplacer("-", "", ".", "").Replace(s)) > 38 {
		return "", false
	}
	r := refRat(s)
	if strings.HasPrefix(s, "-") && r.Sign() == 0 {
		return "", false
	}
	x := new(big.Rat).Mul(r, new(big.Rat).SetInt(pow10(scale)))
	if !x.IsInt() {
		return "", false
	}
	return refFormat(x.Num(), scale), true
}

func refAllocate(total string, weights []string, scale int) []string {
	t := refRat(total)
	units := new(big.Rat).Mul(new(big.Rat).Abs(t), new(big.Rat).SetInt(pow10(scale)))
	n := new(big.Int).Quo(units.Num(), units.Denom())
	sum := new(big.Rat)
	for _, w := range weights {
		sum.Add(sum, refRat(w))
	}
	base := make([]*big.Int, len(weights))
	rems := make([]*big.Rat, len(weights))
	given := new(big.Int)
	for i, w := range weights {
		share := new(big.Rat).Quo(new(big.Rat).Mul(new(big.Rat).SetInt(n), refRat(w)), sum)
		base[i] = new(big.Int).Quo(share.Num(), share.Denom())
		rems[i] = new(big.Rat).Sub(share, new(big.Rat).SetInt(base[i]))
		given.Add(given, base[i])
	}
	left := new(big.Int).Sub(n, given).Int64()
	for ; left > 0; left-- {
		best := -1
		for i := range rems {
			if rems[i] != nil && (best < 0 || rems[i].Cmp(rems[best]) > 0) {
				best = i
			}
		}
		base[best].Add(base[best], big.NewInt(1))
		rems[best] = nil
	}
	out := make([]string, len(base))
	for i, b := range base {
		if t.Sign() < 0 {
			b.Neg(b)
		}
		out[i] = refFormat(b, scale)
	}
	return out
}

func TestMoneyVectors(t *testing.T) {
	for _, raw := range load(t, "money").Cases {
		var c struct {
			ID, Kind, Value, Mode, Unit, Result, Formatted, Total string
			Scale                                                 int
			Valid                                                 bool
			Weights, Parts                                        []string
		}
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		var got any
		var want any
		switch c.Kind {
		case "parse":
			f, ok := refParseAmount(c.Value, c.Scale)
			got, want = [2]any{ok, f}, [2]any{c.Valid, c.Formatted}
		case "round":
			got, want = refFormat(refUnits(refRat(c.Value), c.Scale, c.Mode), c.Scale), c.Result
		case "cash":
			unit := refRat(c.Unit)
			multiples := refRoundRat(new(big.Rat).Quo(refRat(c.Value), unit), c.Mode)
			cash := new(big.Rat).Mul(new(big.Rat).SetInt(multiples), unit)
			got, want = refFormat(refUnits(cash, c.Scale, c.Mode), c.Scale), c.Result
		case "allocate":
			got, want = strings.Join(refAllocate(c.Total, c.Weights, c.Scale), " "), strings.Join(c.Parts, " ")
		default:
			t.Errorf("%s: unknown kind %q", c.ID, c.Kind)
			continue
		}
		if got != want {
			t.Errorf("%s: %v, the vector says %v", c.ID, got, want)
		}
	}
}

func TestBusinessDateVectors(t *testing.T) {
	for _, raw := range load(t, "business-date").Cases {
		var c struct{ ID, Instant, TZ, Date string }
		if err := json.Unmarshal(raw, &c); err != nil {
			t.Fatal(err)
		}
		at, err := time.Parse(time.RFC3339, c.Instant)
		loc, lerr := time.LoadLocation(c.TZ)
		if err != nil || lerr != nil {
			t.Fatalf("%s: %v %v", c.ID, err, lerr)
		}
		if got := at.In(loc).Format(time.DateOnly); got != c.Date {
			t.Errorf("%s: %s, the vector says %s", c.ID, got, c.Date)
		}
	}
}
