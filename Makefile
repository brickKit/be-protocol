# be-protocol: every target runs in a throwaway container; nothing is installed on the host.
# `make check` is what a change to this repository must pass before it is tagged.
#
#   make check          validate + xref + ddl + lint-proto + lint-openapi + vet + vectors-fresh + vectors-sums + vectors-xcheck
#   make vectors        regenerate every vector file and SHA256SUMS (then commit them)
#   DDLTEST_PREFIX=…    container name prefix for the DDL test (default be-protocol-ddltest)

PYTHON   := python:3.13-slim
BUF      := bufbuild/buf:1.57.0
REDOCLY  := redocly/cli:1.34.3
GO       := golang:1.22-alpine
UID      := $(shell id -u):$(shell id -g)
RUN      := docker run --rm -u $(UID) -e HOME=/tmp -v $(CURDIR):/w -w /w
PYDEPS   := jsonschema==4.25.1 pyyaml==6.0.3
PIP      := pip install -q --target /tmp/py $(PYDEPS) >/dev/null 2>&1 && PYTHONPATH=/tmp/py PYTHONDONTWRITEBYTECODE=1
AREAS    := money idempotency envelope calendar numbering errors config redaction
OPENAPI  := openapi/ops.yaml openapi/resource-authz.yaml openapi/resource-lifecycle.yaml \
            fixtures/widget/contracts/widget.openapi.yaml fixtures/peer/contracts/peer.openapi.yaml

.PHONY: check validate xref ddl lint-proto lint-openapi vet vectors vectors-fresh vectors-sums vectors-xcheck

check: validate xref ddl lint-proto lint-openapi vet vectors-fresh vectors-sums vectors-xcheck
	@echo "make check: all green"

# JSON Schemas, catalogues, examples, fixtures, vector files, tables that must agree, mirrors and links
validate:
	$(RUN) -e PIP_CACHE_DIR=/tmp/pip $(PYTHON) sh -c '$(PIP) python3 scripts/validate.py'

# requirement and case IDs: defined once, cited correctly, en == zh
xref:
	$(RUN) -e PIP_CACHE_DIR=/tmp/pip $(PYTHON) sh -c '$(PIP) python3 scripts/xref.py'

# the reference DDL and the widget migration on PostgreSQL 14 and 16
ddl:
	scripts/ddltest.sh

lint-proto:
	$(RUN) -e BUF_CACHE_DIR=/tmp/buf $(BUF) lint
	$(RUN) -e BUF_CACHE_DIR=/tmp/buf $(BUF) build -o /dev/null

lint-openapi:
	$(RUN) $(REDOCLY) lint $(OPENAPI)

# the Go module that embeds the files (fs.go)
vet:
	$(RUN) -e GOCACHE=/tmp/gocache -e GOFLAGS=-buildvcs=false $(GO) sh -c 'go vet ./... && go build ./... && test -z "$$(gofmt -l .)"'

# regenerate into a copy and compare: the committed vectors are exactly what the generators write
vectors-fresh:
	docker run --rm -u $(UID) -e HOME=/tmp -v $(CURDIR):/w:ro $(PYTHON) sh -c 'cp -r /w/vectors /tmp/v && cd /tmp/v && \
	  for a in $(AREAS); do PYTHONDONTWRITEBYTECODE=1 python3 $$a/gen/gen_$$a.py >/dev/null || exit 1; done && \
	  diff -r /w/vectors /tmp/v && echo "vectors fresh"'

vectors-sums:
	$(RUN) -w /w/vectors $(PYTHON) sh -c 'sha256sum -c --quiet SHA256SUMS && echo "SHA256SUMS ok"'

# every case recomputed by an independent implementation (Go, Node)
vectors-xcheck:
	$(MAKE) -C vectors xcheck

vectors:
	$(RUN) $(PYTHON) sh -c 'cd vectors && for a in $(AREAS); do PYTHONDONTWRITEBYTECODE=1 python3 $$a/gen/gen_$$a.py || exit 1; done'
	$(MAKE) -C vectors sums
