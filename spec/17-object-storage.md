[English](17-object-storage.md) · [中文](17-object-storage.zh.md)

# P17 Object storage

Files, attachments, exports and large payloads live in object storage behind the S3 API, one bucket and one credential per component.

## Requirements

| ID | Level | Requirement | Cases |
|---|---|---|---|
| P17.1 | MUST | Object storage is reached through the S3 API at `S3_URL` (`S3_REGION`, `S3_FORCE_PATH_STYLE`); browsers reach it at `S3_PUBLIC_URL`. Each component has its own bucket `S3_BUCKET` and its own credential (the files `S3_ACCESS_KEY_ID_FILE` and `S3_SECRET_ACCESS_KEY_FILE`, re-read as a pair, [P2.9](02-configuration.md)), whose policy allows only that bucket | CP-BLOB-02 |
| P17.2 | MUST | Large content never travels in a gRPC or REST body: the component returns a presigned URL valid for at most 300 s, or an attachment ID. Presigned URLs are issued only after the caller's authorization was checked, are signed for `S3_PUBLIC_URL` (the address browsers reach; default `S3_URL`), and are never logged in full (the signature is redacted). A presigned `PUT` signs `Content-Type` and the exact `Content-Length` declared; a browser form upload uses a presigned `POST` whose policy carries `content-length-range`. Buckets are never publicly readable | CP-BLOB-01, CP-BLOB-02, CP-BLOB-03 |
| P17.3 | MUST | An event that refers to large content carries a claim check `{key, sha256, size}`, never the content and never a URL ([P12.2](12-events.md)); a consumer asks the producer's rpc for a presigned URL valid for at most 300 s (P17.2) | — |

## Notes

- The S3 API is the port: RustFS, MinIO, AWS S3 and Alibaba Cloud OSS are interchangeable by address.
- The lifecycle engine's cold store writes under the component's own bucket ([P16](16-data-lifecycle.md)).
