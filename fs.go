// Package protocol hands out the component protocol's machine-readable parts: the semantic vectors, the JSON Schemas and
// the SDK's own migration files.
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

// Migrations holds the SDK's own migration files (chapter 05, P5.12): every SDK applies these same files.
//
//go:embed migrations
var Migrations embed.FS

// BusMigrations holds the PostgreSQL queue transport's tables (chapter 06), applied to the bus database's schema.
//
//go:embed migrations-bus
var BusMigrations embed.FS

// Data holds shared data files: data/pinyin.tsv, the readings every SDK uses for search columns (chapter 09).
//
//go:embed data
var Data embed.FS

// Version is the protocol version this tree describes.
const Version = "3.0.0-alpha.18"

// Capabilities is capabilities.json: every rule of spec/ belongs to exactly one capability, and each SDK marks the
// status of the SDK-owned ones in its own features.json (the feature matrix, protocol 18).
//
//go:embed capabilities.json
var Capabilities []byte
