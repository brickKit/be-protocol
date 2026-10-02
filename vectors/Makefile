# Regenerate and cross-check the vectors. Run from tools/be-protocol/vectors.
#   make gen      regenerate every *.json from vectors/<area>/gen/gen_*.py (Python >= 3.11, standard library only)
#   make xcheck   recompute every case independently in throwaway containers (Go, Node)
#   make sums     rewrite SHA256SUMS
#   make all      gen + xcheck + sums
AREAS   := money idempotency envelope calendar numbering errors config redaction
PYTHON  ?= PYTHONDONTWRITEBYTECODE=1 python3
DOCKER  ?= docker
GO_IMG  ?= golang:1.22-alpine
NODE_IMG?= node:22-alpine
RUN_GO   = $(DOCKER) run --rm -v "$(CURDIR)":/v:ro -w /v -e GOCACHE=/tmp/gocache -e GOFLAGS=-buildvcs=false $(GO_IMG) go run
RUN_NODE = $(DOCKER) run --rm -v "$(CURDIR)":/v:ro $(NODE_IMG)

.PHONY: all gen xcheck sums check-sums
all: gen xcheck sums

gen:
	@for a in $(AREAS); do $(PYTHON) $$a/gen/gen_$$a.py || exit 1; done

xcheck:
	$(RUN_GO) money/gen/xcheck_money.go money
	$(RUN_GO) errors/gen/xcheck_errors.go errors
	$(RUN_GO) config/gen/xcheck_config.go config
	$(RUN_NODE) sh -c 'mkdir /w && cd /w && npm init -y >/dev/null && npm i --silent canonicalize@2 >/dev/null 2>&1 \
	  && cp /v/idempotency/gen/xcheck_idempotency.mjs . && node xcheck_idempotency.mjs /v/idempotency'
	$(RUN_NODE) node /v/envelope/gen/xcheck_envelope.mjs /v/envelope
	$(RUN_NODE) node /v/calendar/gen/xcheck_calendar.mjs /v/calendar
	$(RUN_NODE) node /v/numbering/gen/xcheck_numbering.mjs /v/numbering
	$(RUN_NODE) node /v/redaction/gen/xcheck_redaction.mjs /v/redaction

sums:
	@find . -name '*.json' -not -path './*/gen/*' | LC_ALL=C sort | xargs sha256sum | sed 's| \./| |' > SHA256SUMS
	@wc -l < SHA256SUMS | xargs echo "files in SHA256SUMS:"

check-sums:
	@sha256sum -c --quiet SHA256SUMS && echo "SHA256SUMS ok"
