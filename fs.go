// Package protocol hands out the component protocol's machine-readable parts: the semantic vectors and the JSON Schemas.
// SDKs import this module at an exact version and run their L1 tests against the vectors (protocol 18).
package protocol

import "embed"

// Vectors holds every vectors/*.json file and vectors/SHA256SUMS.
//
//go:embed vectors
var Vectors embed.FS

// Schemas holds the JSON Schemas under schemas/.
//
//go:embed schemas
var Schemas embed.FS

// Version is the protocol version this tree describes.
const Version = "3.0.0-alpha.1"
