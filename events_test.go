package protocol

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"hash/fnv"
	"reflect"
	"strconv"
	"strings"
	"testing"
)

func TestPartitionVectors(t *testing.T) {
	for _, raw := range load(t, "partition").Cases {
		var c struct {
			ID, Hash   string
			RecordID   string `json:"record_id"`
			Partitions uint64
			Expect     uint64
		}
		_ = json.Unmarshal(raw, &c)
		h := fnv.New64a()
		h.Write([]byte(strings.ToLower(c.RecordID)))
		sum := h.Sum64()
		if strconv.FormatUint(sum, 10) != c.Hash || sum%c.Partitions != c.Expect {
			t.Errorf("%s: hash %s partition %d, recomputed %d %d", c.ID, c.Hash, c.Expect, sum, sum%c.Partitions)
		}
	}
}

func TestEnvelopeVectors(t *testing.T) {
	for _, raw := range load(t, "envelope").Cases {
		var c struct {
			ID    string
			Event struct {
				EventID     string `json:"event_id"`
				Source      string
				Type        string
				Time        string
				RecordID    string `json:"record_id"`
				Stream      string
				Partition   int
				Impl        string
				Epoch       [2]int64
				Seq         int64
				Version     int64
				Projection  string
				Hops        int
				Payload     string
				Causation   string
				LegalEntity string `json:"legal_entity"`
				Subjects    []string
				Claim       bool
				Traceparent string
			}
			Expect struct {
				Headers map[string]string
				Digest  string
				Subject string
			}
		}
		_ = json.Unmarshal(raw, &c)
		e := c.Event
		sum := sha256.Sum256(append(append([]byte(e.EventID), 0), e.Payload...))
		digest := hex.EncodeToString(sum[:])
		h := map[string]string{"ce-specversion": "1.0", "ce-id": e.EventID, "ce-source": "urn:be:" + e.Source,
			"ce-type": e.Type, "ce-time": e.Time, "ce-subject": e.RecordID, "ce-datacontenttype": "application/json",
			"ce-bestream": e.Stream, "ce-bepartition": strconv.Itoa(e.Partition), "ce-beimpl": e.Impl,
			"ce-beepoch": strconv.FormatInt(e.Epoch[0], 10) + "." + strconv.FormatInt(e.Epoch[1], 10),
			"ce-beseq": strconv.FormatInt(e.Seq, 10), "ce-beversion": strconv.FormatInt(e.Version, 10),
			"ce-beprojection": e.Projection, "ce-bedigest": digest, "ce-behops": strconv.Itoa(e.Hops)}
		if e.Causation != "" {
			h["ce-becausation"] = e.Causation
		}
		if e.LegalEntity != "" {
			h["ce-belegalentity"] = e.LegalEntity
		}
		if e.Subjects != nil {
			b, _ := json.Marshal(e.Subjects)
			h["ce-besubjects"] = string(b)
		}
		if e.Claim {
			h["ce-beclaim"] = "true"
		}
		if e.Traceparent != "" {
			h["ce-traceparent"] = e.Traceparent
		}
		if !reflect.DeepEqual(h, c.Expect.Headers) || digest != c.Expect.Digest ||
			c.Expect.Subject != "be."+e.Stream+"."+strconv.Itoa(e.Partition)+"."+e.Type {
			t.Errorf("%s: recomputed headers %v digest %s", c.ID, h, digest)
		}
	}
}
