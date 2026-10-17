"""Chapter 06: partitions and the envelope (P6.1, P6.4, P6.9, P6.13)."""
import hashlib
import json

from common import write


# ---------------------------------------------------------------- events (P6.1, P6.4, P6.9, P6.13)
def fnv1a64(b):
    h = 0xcbf29ce484222325
    for x in b:
        h ^= x
        h = (h * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return h


def partition_vectors():
    ids = ["0190f3a1-7b2c-7def-8a01-23456789abcd", "0190F3A1-7B2C-7DEF-8A01-23456789ABCD",
           "00000000-0000-0000-0000-000000000000", "ffffffff-ffff-ffff-ffff-ffffffffffff",
           "0192a3b4-c5d6-7e8f-9a0b-1c2d3e4f5a6b", "019abcde-f012-7345-8678-9abcdef01234"]
    cases = []
    for rid in ids:
        canon = rid.lower()
        h = fnv1a64(canon.encode())
        for n in (1, 2, 4, 7, 16, 256):
            cases.append({"id": f"{canon[:8]}-{'upper' if rid != canon else 'lower'}-{n}", "record_id": rid,
                          "partitions": n, "hash": str(h), "expect": h % n})
    write("partition", ["P6.1"],
          "分区 = FNV-1a 64 位（记录身份转成小写后的 UTF-8 字节）对分区数取余。hash 是 64 位无符号的十进制字符串（避免 JSON 数字丢精度）；"
          "大写的身份与小写的落在同一分区。",
          cases, {"record_id": "记录身份", "partitions": "流声明的分区数", "hash": "FNV-1a 64 位，十进制字符串",
                  "expect": "分区"})


def envelope_vectors():
    import hashlib as _h
    base = {"event_id": "0190f3a1-7b2c-7def-8a01-23456789abcd", "source": "erp/inventory",
            "type": "erp.inventory.stock_moved.v1", "time": "2026-10-17T08:30:00.123Z",
            "record_id": "0190f3a1-0000-7000-8000-000000000001", "stream": "erp.inventory.stock", "partition": 3,
            "impl": "6f1c2d3e-4a5b-4c6d-8e7f-901234567890", "epoch": [1, 1], "seq": 42, "version": 7,
            "projection": "full", "hops": 0, "payload": '{"qty":"5.000","sku":"A-1"}'}
    variants = [
        ("full-state", {}),
        ("caused-by-another-event", {"causation": "0190f3a0-1111-7222-8333-444455556666", "hops": 3}),
        ("transaction-fact-with-legal-entity", {"legal_entity": "LE1", "projection": "partial"}),
        ("watermark-source-subjects", {"subjects": ["acc:01", "org:7"], "type": "mdm.org.unit_changed.v1",
                                        "source": "mdm/org", "stream": "mdm.org.units"}),
        ("delete", {"projection": "delete", "payload": "{}", "version": 8}),
        ("new-epoch", {"epoch": [2, 3], "seq": 1}),
        ("claim-check", {"claim": True, "payload": '{"claim":{"uri":"s3://b/k","size":70000,"sha256":"' + "0" * 64 + '"}}'}),
        ("with-trace", {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}),
    ]
    cases = []
    for name, v in variants:
        e = dict(base, **v)
        payload = e["payload"].encode()
        digest = _h.sha256(e["event_id"].encode() + b"\x00" + payload).hexdigest()
        h = {"ce-specversion": "1.0", "ce-id": e["event_id"], "ce-source": "urn:be:" + e["source"], "ce-type": e["type"],
             "ce-time": e["time"], "ce-subject": e["record_id"], "ce-datacontenttype": "application/json",
             "ce-bestream": e["stream"], "ce-bepartition": str(e["partition"]), "ce-beimpl": e["impl"],
             "ce-beepoch": f"{e['epoch'][0]}.{e['epoch'][1]}", "ce-beseq": str(e["seq"]),
             "ce-beversion": str(e["version"]), "ce-beprojection": e["projection"], "ce-bedigest": digest,
             "ce-behops": str(e["hops"])}
        if "causation" in e:
            h["ce-becausation"] = e["causation"]
        if "legal_entity" in e:
            h["ce-belegalentity"] = e["legal_entity"]
        if "subjects" in e:
            h["ce-besubjects"] = json.dumps(e["subjects"], separators=(",", ":"))
        if e.get("claim"):
            h["ce-beclaim"] = "true"
        if "traceparent" in e:
            h["ce-traceparent"] = e["traceparent"]
        cases.append({"id": name, "event": e, "expect": {"headers": h, "digest": digest,
                                                         "subject": f"be.{e['stream']}.{e['partition']}.{e['type']}"}})
    write("envelope", ["P6.4", "P6.9", "P6.13", "P6.17"],
          "一条发件行发布成什么：消息头（CloudEvents 二进制模式，ce- 前缀）、行摘要（SHA-256（事件身份、0 字节、载荷字节），小写十六进制）"
          "与主题。event.payload 是载荷的确切字节（UTF-8）；epoch 是（代次，时间线）。besubjects 是紧凑 JSON（无空白）。"
          "消息头逐个相等，不多不少。",
          cases, {"event": "发件行的字段", "expect.headers": "消息头", "expect.digest": "行摘要", "expect.subject": "主题"})
