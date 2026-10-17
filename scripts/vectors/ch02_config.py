"""Chapter 02: configuration parsing (P2.4, P2.5)."""
import re

from common import write


# ---------------------------------------------------------------- config parse (P2.4, P2.5)
DUR = re.compile(r"^(0|[1-9][0-9]*)(ms|s|m|h)$")
INT = re.compile(r"^-?(0|[1-9][0-9]*)$")


def parse(t, v, required, default, values=None):
    if v is None or v == "":
        if required:
            return {"error": "missing"}
        return {"value": default}
    if t == "string":
        return {"value": v}
    if t == "integer":
        return {"value": int(v)} if INT.match(v) and v != "-0" else {"error": "invalid"}
    if t == "boolean":
        return {"value": v == "true"} if v in ("true", "false") else {"error": "invalid"}
    if t == "duration":
        m = DUR.match(v)
        if not m:
            return {"error": "invalid"}
        mult = {"ms": 1, "s": 1000, "m": 60000, "h": 3600000}[m.group(2)]
        return {"value": int(m.group(1)) * mult}
    if t == "enum":
        return {"value": v} if v in values else {"error": "unknown_enum"}
    raise ValueError(t)


def config_parse_vectors():
    rows = [
        ("string-plain", "string", "abc", True, None, None), ("string-spaces-kept", "string", " a b ", True, None, None),
        ("required-unset", "string", None, True, None, None), ("required-empty", "string", "", True, None, None),
        ("optional-unset-default", "string", None, False, "x", None), ("optional-empty-default", "integer", "", False, 7, None),
        ("int-zero", "integer", "0", True, None, None), ("int-negative", "integer", "-42", True, None, None),
        ("int-plus", "integer", "+1", True, None, None), ("int-leading-zero", "integer", "007", True, None, None),
        ("int-space", "integer", " 1", True, None, None), ("int-minus-zero", "integer", "-0", True, None, None),
        ("int-invalid-not-default", "integer", "abc", False, 7, None),
        ("bool-true", "boolean", "true", True, None, None), ("bool-false", "boolean", "false", True, None, None),
        ("bool-upper", "boolean", "TRUE", True, None, None), ("bool-one", "boolean", "1", True, None, None),
        ("bool-yes", "boolean", "yes", True, None, None),
        ("dur-ms", "duration", "1500ms", True, None, None), ("dur-s", "duration", "3s", True, None, None),
        ("dur-m", "duration", "2m", True, None, None), ("dur-h", "duration", "1h", True, None, None),
        ("dur-zero", "duration", "0s", True, None, None), ("dur-fraction", "duration", "1.5s", True, None, None),
        ("dur-compound", "duration", "1m30s", True, None, None), ("dur-no-unit", "duration", "30", True, None, None),
        ("dur-us", "duration", "10us", True, None, None),
        ("enum-ok", "enum", "warn", True, None, ["debug", "info", "warn", "error"]),
        ("enum-case", "enum", "WARN", True, None, ["debug", "info", "warn", "error"]),
        ("enum-unset-default", "enum", None, False, "info", ["debug", "info", "warn", "error"]),
    ]
    cases = []
    for cid, t, v, req, d, vals in rows:
        c = {"id": cid, "type": t, "value": v, "required": req, "default": d}
        if vals:
            c["values"] = vals
        c["expect"] = parse(t, v, req, d, vals)
        cases.append(c)
    write("config-parse", ["P2.4", "P2.5"],
          "配置值的严格解析。value 为 null 表示未设置；expect.value 是解析结果（duration 以毫秒表示），expect.error 是错误类别（missing、invalid、unknown_enum）。不合法的值不回退到缺省值。",
          cases, {"type": "string | integer | boolean | duration | enum", "value": "原始字符串或 null", "required": "是否必填",
                  "default": "声明的缺省值", "values": "enum 的取值", "expect": "{value} 或 {error}"})
