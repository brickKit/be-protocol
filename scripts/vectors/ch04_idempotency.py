"""Chapter 04 vectors for command idempotency keys: key validity and the request fingerprint (P4.21, P4.22)."""
import hashlib
import unicodedata

from ch08_canonical import digest
from common import write


def valid_key(k):
    return 1 <= len(k) <= 255 and all(0x21 <= ord(c) <= 0x7E for c in k)


def fingerprint(principal, operation, target, body):
    nfc = lambda s: unicodedata.normalize("NFC", s)  # noqa: E731
    return digest("be.idempotency.request", 1, {
        "principal": nfc(principal), "operation": nfc(operation), "target": nfc(target),
        "body_sha256": hashlib.sha256(body.encode()).hexdigest()})


def idempotency_vectors():
    user = "0190f3a2-7c1e-7b2a-9d4e-1a2b3c4d5e6f"
    cases = []
    for i, key in enumerate(["k", "order-confirm-0190f3a2", "a" * 255, "", "a" * 256, "has space", "tab\t",
                             "ümlaut", "~!#$%&'*+-.^_`|"]):
        cases.append({"id": f"key-{i:02d}", "kind": "key", "key": key, "valid": valid_key(key)})
    requests = [
        ("same-1", user, "erp.sales.order.confirm", "POST /api/orders/7/confirm", '{"revision":3}'),
        ("same-2", user, "erp.sales.order.confirm", "POST /api/orders/7/confirm", '{"revision":3}'),
        ("other-body", user, "erp.sales.order.confirm", "POST /api/orders/7/confirm", '{"revision":4}'),
        ("key-order", user, "erp.sales.order.create", "POST /api/orders", '{"a":1,"b":2}'),
        ("key-order-swapped", user, "erp.sales.order.create", "POST /api/orders", '{"b":2,"a":1}'),
        ("other-target", user, "erp.sales.order.confirm", "POST /api/orders/8/confirm", '{"revision":3}'),
        ("other-principal", "erp/billing", "erp.sales.order.confirm", "POST /api/orders/7/confirm", '{"revision":3}'),
        ("query", user, "erp.sales.order.create", "POST /api/orders?draft=true", ""),
        # plain concatenation of target and body would collide for these two; the canonical object does not
        ("concat-a", user, "x.op", "POST /a/b", "c"),
        ("concat-b", user, "x.op", "POST /a", "/bc"),
        ("grpc", "erp/sales", "erp.inventory.branch.hold", "/be.erp.inventory.v1.Branches/Hold", "\n\x05b-001"),
        ("nfc", user, "x.op", "POST /café", "{}"),
        ("nfc-composed", user, "x.op", "POST /café", "{}"),
    ]
    for cid, principal, op, target, body in requests:
        cases.append({"id": f"fp-{cid}", "kind": "fingerprint", "principal": principal, "operation": op,
                      "target": target, "body": body, "fingerprint": fingerprint(principal, op, target, body)})
    write("idempotency", ["P4.21", "P4.22"],
          "命令的幂等键。kind=key：键是否合格（1–255 个可见 ASCII 字符，0x21–0x7E）。kind=fingerprint：请求指纹 = 规范摘要"
          "（P8.8，记录类型 be.idempotency.request，主版本 1），内容为 principal、operation、target 与 body_sha256"
          "（请求体原始字节的 SHA-256 小写十六进制；这里取 body 的 UTF-8 字节）；文本先做 NFC。请求体按字节比较，"
          "换了 JSON 键的顺序就是另一个请求；concat-a 与 concat-b 直接拼接会相同，规范对象不相同。",
          cases, {"key": "kind=key：键与是否合格",
                  "fingerprint": "kind=fingerprint：请求与它的指纹"})
