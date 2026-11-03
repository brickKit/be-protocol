.PHONY: check vectors proto-lint
# buf runs in a throwaway container (nothing installed locally), the same image the contract repositories pin.
BUF := bufbuild/buf:1.74.0@sha256:621f108266b19236906aa328e64b7c50340738472c5da4d4b25104f01aa8d204
RUN := docker run --rm -u $(shell id -u):$(shell id -g) -e HOME=/tmp -e BUF_CACHE_DIR=/tmp/buf -v $(CURDIR):/w -w /w

check: proto-lint  ## structure, SHA256SUMS, the reference recomputation of every vector, the protobuf style
	go vet ./...
	go test ./...
vectors:  ## regenerate vectors/*.json and vectors/SHA256SUMS
	python3 -I scripts/gen-vectors.py
proto-lint:  ## proto/ against buf STANDARD
	$(RUN) $(BUF) lint
