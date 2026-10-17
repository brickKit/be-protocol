"""Chapter 09: search normalization and keyset pages (P9.1-P9.9)."""
import base64
import hashlib
import json
import pathlib
import unicodedata

from common import ROOT, write

PINYIN = {}
for line in (ROOT / "data" / "pinyin.tsv").read_text().splitlines():
    if line.startswith("#"):
        continue
    cp, reading = line.split("\t")
    PINYIN[int(cp, 16)] = reading

SEP = "\x1f"


def fold(s):
    """NFKC (full-width to half-width), lower case, control and format characters (Cc, Cf) dropped."""
    s = unicodedata.normalize("NFKC", s).lower()
    return "".join(c for c in s if unicodedata.category(c) not in ("Cc", "Cf"))


def search_text(values):
    parts = []
    for v in values:
        f = fold(v)
        full = "".join(PINYIN.get(ord(c), c) for c in f)
        initials = "".join(PINYIN[ord(c)][0] if ord(c) in PINYIN else c for c in f)
        parts += [f, full, initials]
    return SEP.join(parts)


def query(q):
    return fold(q).strip()


def matches(values, q):
    n = query(q)
    return n == "" or any(n in part for part in search_text(values).split(SEP))


def search_vectors():
    cases = []
    for cid, vals in [("chinese", ["中国银行"]), ("mixed", ["ERP系统 v2"]), ("full-width", ["ＡＢＣ１２３"]),
                      ("polyphonic-first-reading", ["重庆", "乐行"]), ("several-fields", ["上海", "Acme 有限公司"]),
                      ("controls-dropped", ["a\tb\u0001c"])]:
        cases.append({"id": "text-" + cid, "kind": "text", "values": vals, "expect": search_text(vals)})
    for cid, q in [("blank", "  "), ("upper", "ZhongGuo"), ("full-width", "ＺＧ"), ("literal-percent", "50%_off")]:
        cases.append({"id": "query-" + cid, "kind": "query", "q": q, "expect": query(q)})
    for cid, vals, q in [("by-han", ["中国银行"], "银行"), ("by-full-pinyin", ["中国银行"], "zhongguo"),
                         ("by-initials", ["中国银行"], "zgyx"),
                         ("polyphone-takes-the-first-reading", ["中国银行"], "zgyh"), ("by-latin", ["ERP系统"], "erp"),
                         ("no-match-across-parts", ["中国银行"], "zhonggyh"), ("blank-matches-all", ["x"], " "),
                         ("percent-is-literal", ["100% cotton"], "100%"), ("percent-not-wildcard", ["100 cotton"], "100%"),
                         ("underscore-literal", ["a_b"], "a_b"), ("underscore-not-wildcard", ["axb"], "a_b")]:
        cases.append({"id": "match-" + cid, "kind": "match", "values": vals, "q": q, "expect": matches(vals, q)})
    write("search", ["P9.6", "P9.7"],
          "列表内搜索的规范化（版本 1）：一个字段值折叠为 NFKC、小写、去掉控制与格式字符（Unicode 类别 Cc、Cf）；全拼把每个汉字换成 data/pinyin.tsv 中的读音（每字首选读音、"
          "无声调），其他字符不变；首字母取读音的首字母。搜索列 = 各字段的（折叠原文、全拼、首字母）依次用 U+001F 连接。查询 q 同样折叠并去掉首尾空白，"
          "为空即没有条件；匹配 = q 是搜索列中某一段的子串（不跨段），% 与 _ 按字面。kind=text 给出搜索列，query 给出规范化的 q，match 给出是否匹配。",
          cases, {"values": "组成搜索列的字段值", "q": "查询", "expect": "搜索列文本、规范化的 q，或是否匹配"})


ROWS = [{"id": f"0190f3a1-0000-7000-8000-0000000000{i:02x}", "name": n, "amount": a, "day": d}
        for i, (n, a, d) in enumerate([("beta", "10", "2026-10-01"), ("alpha", "10", "2026-10-02"), ("gamma", "5", "2026-10-02"),
                                       ("alpha", "7.5", "2026-10-03"), ("delta", "10", "2026-10-01"), ("beta", "-1", "2026-10-04"),
                                       ("epsilon", "100", "2026-10-02"), ("alpha", "10", "2026-10-02")], start=1)]


def sort_key(row, order):
    from decimal import Decimal
    key = []
    for o in order:
        v = row[o["field"]]
        v = Decimal(v) if o["field"] == "amount" else v
        key.append((v, o["dir"]))
    return key


def ordered(rows, order):
    import functools

    def cmp(a, b):
        for o in order + [{"field": "id", "dir": "asc"}]:
            from decimal import Decimal
            x, y = a[o["field"]], b[o["field"]]
            if o["field"] == "amount":
                x, y = Decimal(x), Decimal(y)
            if x != y:
                r = -1 if x < y else 1
                return r if o["dir"] == "asc" else -r
        return 0
    return sorted(rows, key=functools.cmp_to_key(cmp))


def pages_vectors():
    cases = [{"id": "fixture", "kind": "fixture", "rows": ROWS,
              "fields": {"name": "text", "amount": "decimal", "day": "date"}}]
    for cid, order, size in [("by-name", [{"field": "name", "dir": "asc"}], 3),
                             ("by-amount-desc", [{"field": "amount", "dir": "desc"}], 3),
                             ("mixed-directions", [{"field": "day", "dir": "desc"}, {"field": "name", "dir": "asc"}], 2),
                             ("ties-broken-by-id", [{"field": "amount", "dir": "asc"}], 2),
                             ("one-page", [{"field": "name", "dir": "desc"}], 50),
                             ("default-order", [], 4)]:
        rows = ordered(ROWS, order)
        pages = [[r["id"] for r in rows[i:i + size]] for i in range(0, len(rows), size)]
        cases.append({"id": cid, "kind": "pages", "sort": order, "page_size": size, "expect": pages})
    for cid, size in [("page-size-zero", 0), ("page-size-over-limit", 201)]:
        cases.append({"id": cid, "kind": "refused", "sort": [], "page_size": size, "expect": "REQUEST_INVALID"})
    write("list-pages", ["P9.1", "P9.2", "P9.3"],
          "游标分页：fixture 给出记录与字段类型（decimal 按数值比较，text 按字节，date 按日期）。kind=pages：按 sort 排序、记录身份升序作最后的比较键，"
          "每页 page_size 行，逐页沿游标取到底，expect 是每页的身份；sort 为空表示只按身份升序。kind=refused：页大小 0 或超过 200 被拒。"
          "游标内容不在本向量中（不透明，只要求跨语言能按语义继续）。",
          cases, {"rows": "记录", "sort": "排序键与方向", "page_size": "页大小", "expect": "每页的记录身份，或拒绝的 reason"})


def apply(cur, inp):
    """Protocol 02's receiving rules for one row (same implementation instance and epoch unless marked old)."""
    k, v = inp["kind"], inp["version"]
    if cur is None:
        return {"full": ("complete", v, None, "write"), "partial": ("incomplete", v, v, "write_and_fetch"),
                "delete": ("tombstone", v, None, "write")}[k]
    st, ver, need = cur["state"], cur["version"], cur.get("need_version")
    if cur.get("old"):  # the local row belongs to an older epoch or implementation instance
        if k == "partial":
            return ("incomplete", v, v, "write_and_fetch")
        return ({"full": "complete", "delete": "tombstone"}[k], v, None, "overwrite")
    if st == "tombstone":
        if v <= ver:
            return (st, ver, None, "ignore")
        return {"full": ("complete", v, None, "overwrite"), "partial": ("incomplete", v, v, "write_and_fetch"),
                "delete": ("tombstone", v, None, "write")}[k]
    if k == "full":
        if st == "complete":
            return ("complete", v, None, "overwrite") if v > ver else (st, ver, None, "ignore")
        return ("complete", v, None, "overwrite") if v >= need else (st, ver, need, "ignore")
    if k == "partial":
        return ("incomplete", v, v, "merge_and_fetch") if v > ver else (st, ver, need, "ignore")
    return ("tombstone", v, None, "write") if v >= ver else (st, ver, need, "ignore")


def projection_vectors():
    currents = {"none": None, "complete-5": {"state": "complete", "version": 5},
                "incomplete-5-need-7": {"state": "incomplete", "version": 5, "need_version": 7},
                "tombstone-5": {"state": "tombstone", "version": 5},
                "old-epoch-complete-9": {"state": "complete", "version": 9, "old": True}}
    cases = []
    for cname, cur in currents.items():
        for kind in ("full", "partial", "delete"):
            for v in (4, 5, 6, 7, 8):
                st, ver, need, action = apply(cur, {"kind": kind, "version": v})
                exp = {"state": st, "version": ver, "action": action}
                if need is not None:
                    exp["need_version"] = need
                cases.append({"id": f"{cname}-{kind}-v{v}", "current": cur, "input": {"kind": kind, "version": v},
                              "expect": exp})
    write("projection-apply", ["P9.11"],
          "投影行的接收（装配项目协议 02 的状态迁移表）：current 是本地行（null 为没有；old 表示属于旧纪元或旧实现实例），input 是到达的事件或读取"
          "（full 完整状态、partial 部分字段、delete 删除）及其版本；expect 是之后的状态、版本、需要的版本（incomplete 时）与动作：write、overwrite、"
          "merge_and_fetch、write_and_fetch（排入取回）、ignore。",
          cases, {"current": "本地行", "input": "到达的输入", "expect": "结果"})
