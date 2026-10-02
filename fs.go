// Package beprotocol exposes the files of the BrickEnterprise component protocol to Go tests and
// tools (be-acceptance, be-sdk-go): the specification, schemas, reference DDL, proto and OpenAPI
// fragments, semantic vectors and the fixture-component contract. It contains no logic.
package beprotocol

import "embed"

// Version is the protocol version this module describes (MAJOR.MINOR).
const Version = "1.0"

// FS holds the protocol files at their repository paths, for example
// "schemas/errors-be.yaml", "ddl/02-outbox.sql" or "vectors/money/round.json".
//
//go:embed spec schemas ddl proto openapi vectors fixtures
var FS embed.FS
