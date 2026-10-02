[English](17-object-storage.md) · [中文](17-object-storage.zh.md)

# P17 对象存储

文件、附件、导出和大载荷放在 S3 API 背后的对象存储里，每个组件一个 bucket、一套凭据。

## 要求

| ID | 等级 | 要求 | 用例 |
|---|---|---|---|
| P17.1 | MUST | 通过 S3 API 访问对象存储，地址是 `S3_URL`（`S3_REGION`、`S3_FORCE_PATH_STYLE`）；浏览器通过 `S3_PUBLIC_URL` 访问。每个组件有自己的 bucket `S3_BUCKET` 和自己的凭据（`S3_ACCESS_KEY_ID`、`S3_SECRET_ACCESS_KEY`），凭据的策略只允许访问这个 bucket | CP-BLOB-02 |
| P17.2 | MUST | 大内容从不放进 gRPC 或 REST 的消息体：组件返回一个有效期最多 300 s 的预签名 URL，或一个附件 ID。预签名 URL 只在调用方的授权检查过之后才签发，按 `S3_PUBLIC_URL`（浏览器能访问的地址；默认 `S3_URL`）签名，并且从不完整地写进日志（签名被脱敏）。预签名的 `PUT` 对 `Content-Type` 和声明的确切 `Content-Length` 签名；浏览器表单上传用预签名的 `POST`，其策略带 `content-length-range`。bucket 从不公开可读 | CP-BLOB-01, CP-BLOB-02, CP-BLOB-03 |
| P17.3 | MUST | 指向大内容的事件携带 claim check `{key, sha256, size}`，从不携带内容本身，也从不携带 URL（[P12.2](12-events.zh.md)）；消费者向生产者的 rpc 要一个最多 300 s 有效的预签名 URL（P17.2） | — |

## 说明

- S3 API 就是端口：RustFS、MinIO、AWS S3 和阿里云 OSS 换个地址就能互换。
- 生命周期引擎的冷存储写在组件自己的 bucket 下（[P16](16-data-lifecycle.zh.md)）。
