#!/usr/bin/env python3
"""Generate vectors/config/*.json (protocol P2; foundations 24; brickKit's
environment-variable contract).

values.json   how a component parses the value of one declared key at start, and a secret file's text
endpoints.json  dependency address variables (names and values) and slot-family address keys
keys.json     which key names a component may declare, and how a secret key is declared
forms.json    value forms written in config/*.yaml (assembly time, be-ops gates)

xcheck_config.go recomputes every case in Go; durations go through the real
time.ParseDuration, so the Go duration syntax is checked against Go itself.
"""

import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "_lib"))
from vecfile import CaseList, area_dir, write_file  # noqa: E402

GEN = "config/gen/gen_config.py"
OUT = area_dir(__file__)
SAFE_INT = (-(2 ** 53 - 1), 2 ** 53 - 1)  # I-JSON (RFC 7493 §2.2): exact in every language
UNITS = {"ns": 1, "us": 1000, "µs": 1000, "μs": 1000, "ms": 10 ** 6, "s": 10 ** 9, "m": 60 * 10 ** 9,
         "h": 3600 * 10 ** 9}
DUR_RE = re.compile(r"([0-9]*(?:\.[0-9]*)?)(ns|us|µs|μs|ms|s|m|h)")
URL_RE = re.compile(r"([a-z][a-z0-9+.-]*)://([^\s/?#@]+@)?([^\s/?#:]+|\[[0-9a-fA-F:]+\])(:[0-9]{1,5})?([/?#][^\s]*)?")


class CfgError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def duration_ns(s):
    """Go's time.ParseDuration, re-implemented: [-+]?(number unit)+ | 0."""
    neg = False
    if s and s[0] in "+-":
        neg = s[0] == "-"
        s = s[1:]
    if s == "0":
        return 0
    if not s:
        raise CfgError("CONFIG_INVALID")
    total = 0
    pos = 0
    while pos < len(s):
        m = DUR_RE.match(s, pos)
        if not m or m.group(1) in ("", "."):
            raise CfgError("CONFIG_INVALID")
        num = m.group(1)
        ip, _, fp = num.partition(".")
        unit = UNITS[m.group(2)]
        whole = int(ip or "0") * unit
        frac = 0
        if fp:
            # Go truncates the fractional part toward zero at nanosecond precision
            frac = int(fp) * unit // 10 ** len(fp)
        total += whole + frac
        if total > 2 ** 63 - 1 + (1 if neg else 0):
            raise CfgError("CONFIG_INVALID")
        pos = m.end()
    return -total if neg else total


def parse_value(inp):
    t = inp["type"]
    v = inp.get("value")
    if v == "" and t != "string":
        v = None  # an empty value for a typed key counts as not set (brickKit's ${NAME:-})
    if v is None:
        if "default" in inp:
            v = inp["default"]
        elif inp.get("required"):
            raise CfgError("CONFIG_MISSING")
        else:
            return {"set": False}
    if not isinstance(v, str):
        raise CfgError("CONFIG_INVALID")
    if t == "string":
        out = v
    elif t == "integer":
        if not re.fullmatch(r"-?[0-9]+", v):
            raise CfgError("CONFIG_INVALID")
        out = int(v)
        if not SAFE_INT[0] <= out <= SAFE_INT[1]:
            raise CfgError("CONFIG_INVALID")
        if "minimum" in inp and out < inp["minimum"]:
            raise CfgError("CONFIG_INVALID")
    elif t == "boolean":
        if v not in ("true", "false", "1", "0"):
            raise CfgError("CONFIG_INVALID")
        out = v in ("true", "1")
    elif t == "duration":
        out = duration_ns(v)
        if out < 0:
            raise CfgError("CONFIG_INVALID")
        out = str(out)  # nanoseconds as a decimal string: int64 does not fit a JSON number exactly
    elif t == "duration_list":
        parts = v.split(",")
        out = []
        for p in parts:
            if p == "" or p != p.strip():
                raise CfgError("CONFIG_INVALID")
            d = duration_ns(p)
            if d <= 0:
                raise CfgError("CONFIG_INVALID")
            out.append(str(d))
    elif t == "url":
        m = URL_RE.fullmatch(v)
        if not m:
            raise CfgError("CONFIG_INVALID")
        if m.group(4) and not 1 <= int(m.group(4)[1:]) <= 65535:
            raise CfgError("CONFIG_INVALID")
        if "schemes" in inp and m.group(1) not in inp["schemes"]:
            raise CfgError("CONFIG_INVALID")
        out = v
    elif t == "json":
        def pairs(ps):
            ks = [k for k, _ in ps]
            if len(ks) != len(set(ks)):
                raise CfgError("CONFIG_INVALID")
            return dict(ps)
        try:
            out = json.loads(v, object_pairs_hook=pairs,
                             parse_constant=lambda c: (_ for _ in ()).throw(CfgError("CONFIG_INVALID")))
        except ValueError:
            raise CfgError("CONFIG_INVALID")
        kind = inp.get("json_kind", "any")
        if kind == "object" and not isinstance(out, dict) or kind == "array" and not isinstance(out, list):
            raise CfgError("CONFIG_INVALID")
    elif t == "enum":
        if v not in inp["enum"]:
            raise CfgError("CONFIG_INVALID")
        out = v
    else:
        raise KeyError(t)
    if inp.get("secret"):
        # P2.7, P2.12: a secret key is declared mount: file; the environment holds the absolute path of
        # the file (/run/brickkit/secrets/<service>/<KEY>, or a host path for mode: local), never the value
        if t != "string" or not v.startswith("/") or v.endswith("/") or "\x00" in v:
            raise CfgError("CONFIG_INVALID")
        return {"set": True, "source": "file", "path": v}
    return {"set": True, "value": out}


def secret_text(inp):
    # P2.9: the text of a secret file; exactly one trailing LF or CRLF is removed, nothing else
    c = inp["content"]
    if c.endswith("\r\n"):
        c = c[:-2]
    elif c.endswith("\n"):
        c = c[:-1]
    if c == "":
        if inp.get("required"):
            raise CfgError("CONFIG_MISSING")
        return {"set": False}
    return {"set": True, "value": c}


def endpoint_name(dep, port):
    if not re.fullmatch(r"[a-z][a-z0-9]*/[a-z][a-z0-9-]*", dep):
        raise CfgError("COMPONENT_INVALID")
    base = dep.upper().replace("/", "_").replace("-", "_")
    if port:
        if not re.fullmatch(r"[a-z][a-z0-9-]*", port):
            raise CfgError("PORT_NAME_INVALID")
        base += "_" + port.upper().replace("-", "_")
    return base + "_ENDPOINT"


def endpoint_value(v):
    if v is None:
        return {"present": False}
    if not v.startswith("http://"):
        raise CfgError("CONFIG_INVALID")
    rest = v[len("http://"):].rstrip("/")
    m = re.fullmatch(r"([a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*):([0-9]{1,5})", rest)
    if not m or not 1 <= int(m.group(5)) <= 65535:
        raise CfgError("CONFIG_INVALID")
    return {"present": True, "address": rest}


FAMILY_KEYS = {"AUTHZ_URL": "http", "AUTHZ_GRPC_URL": "grpc", "IAM_URL": "http", "IAM_GRPC_URL": "grpc"}


def family_address(inp):
    # P2.10: a slot family's address keys hold what $endpoint: writes, http://<host>:<port> (no path); the
    # *_URL key is the REST base, the *_GRPC_URL key the gRPC target once http:// is stripped. No arithmetic.
    key, v = inp["key"], inp.get("value")
    if key not in FAMILY_KEYS:
        raise CfgError("CONFIG_KEY_INVALID")
    if v is None:
        return {"present": False}
    if not isinstance(v, str) or not v.startswith("http://"):
        raise CfgError("CONFIG_INVALID")
    rest = v[len("http://"):].rstrip("/")
    m = re.fullmatch(r"([a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*):([0-9]{1,5})", rest)
    if not m or not 1 <= int(m.group(5)) <= 65535:
        raise CfgError("CONFIG_INVALID")
    if FAMILY_KEYS[key] == "grpc":
        return {"present": True, "target": rest}
    return {"present": True, "base": "http://" + rest}


RESERVED = {"COMPONENT_ID", "COMPONENT_VERSION", "PORT"}


def key_name(k):
    if not isinstance(k, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", k):
        raise CfgError("CONFIG_KEY_INVALID")
    if k in RESERVED or k.endswith("_ENDPOINT") or k.startswith("BRICKKIT_SERVED_MEMBERS"):
        raise CfgError("CONFIG_KEY_RESERVED")
    return {"valid": True}


def key_declaration(inp):
    # P2.12: secret: true <=> mount: file <=> the name ends in _FILE (brickKit: mount needs secret and string)
    k, secret, mount, t = inp["key"], inp.get("secret", False), inp.get("mount"), inp.get("type", "string")
    key_name(k)
    if mount is not None and mount != "file":
        raise CfgError("MOUNT_INVALID")
    if mount == "file" and not secret:
        raise CfgError("MOUNT_NEEDS_SECRET")
    if mount == "file" and t != "string":
        raise CfgError("MOUNT_NEEDS_STRING")
    if secret and mount != "file":
        raise CfgError("SECRET_NOT_FILE")
    if secret and not k.endswith("_FILE"):
        raise CfgError("FILE_SUFFIX_REQUIRED")
    if not secret and k.endswith("_FILE"):
        raise CfgError("FILE_SUFFIX_RESERVED")
    return {"valid": True}


ENDPOINT_RE = re.compile(r"\$endpoint:([a-z][a-z0-9]*)/([^/]*)(/.*)?")


def endpoint_form(w):
    # brickKit's $endpoint:<scope>/<name>[@<version>][:<port name>][/<path>]; the first / after the
    # second ID segment starts the path
    m = ENDPOINT_RE.fullmatch(w)
    if not m:
        raise CfgError("FORM_INVALID")
    name, port, version = m.group(2), None, None
    if ":" in name:
        name, port = name.split(":", 1)
        if not re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", port) or len(port) > 15:
            raise CfgError("FORM_INVALID")
    if "@" in name:
        name, version = name.split("@", 1)
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            raise CfgError("FORM_INVALID")
    if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
        raise CfgError("FORM_INVALID")
    out = {"form": "endpoint", "component": m.group(1) + "/" + name}
    if version:
        out["version"] = version
    if port:
        out["port"] = port
    if m.group(3):
        out["path"] = m.group(3)
    return out


REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^${}]*))?\}")


def value_form(inp):
    w, secret = inp["written"], inp.get("secret", False)
    if isinstance(w, dict):
        if set(w) == {"existingSecret", "key"} and all(isinstance(x, str) and x for x in w.values()):
            if not secret:
                raise CfgError("FORM_NOT_FOR_PLAIN")
            return {"form": "existing_secret", "name": w["existingSecret"], "key": w["key"]}
        raise CfgError("FORM_INVALID")
    if not isinstance(w, str):
        raise CfgError("FORM_INVALID")
    if w.startswith("$var:"):
        name = w[5:]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise CfgError("FORM_INVALID")  # $var: must be the whole value
        return {"form": "var", "name": name}
    if w.startswith("$endpoint:"):
        out = endpoint_form(w)
        if secret:
            raise CfgError("SECRET_NOT_REFERENCE")  # an address is never a secret
        return out
    if w.startswith("file://"):
        p = w[7:]
        if not p or p.startswith("/") or ".." in p.split("/"):
            raise CfgError("FORM_INVALID")
        return {"form": "file", "path": p}
    m = REF.fullmatch(w)
    if m:
        if m.group(2) is not None:
            if secret and m.group(3):
                raise CfgError("SECRET_PLAINTEXT_DEFAULT")
            return {"form": "env", "name": m.group(1), "default": m.group(3)}
        return {"form": "env", "name": m.group(1)}
    rest = REF.sub("", w)
    if "${" in rest or "$var:" in w or "$endpoint:" in w:
        raise CfgError("FORM_INVALID")  # a broken reference, or $var: that is not the whole value
    if secret:
        raise CfgError("SECRET_NOT_REFERENCE")  # project rule: a secret is only ever a reference
    if rest != w:
        return {"form": "template", "names": [g[0] for g in REF.findall(w)]}
    return {"form": "literal"}


def add(c, slug, why, op, inp, fn, refs):
    try:
        c.add(slug, why, op, inp, expected=fn(inp), refs=refs)
    except CfgError as e:
        c.add(slug, why, op, inp, error=e.reason, refs=refs)


def gen_values():
    c = CaseList("config", "values")
    P = lambda t, v, **kw: dict({"type": t, "value": v}, **kw)  # noqa: E731
    rows = [
        # presence, defaults, required
        ("absent-default", P("integer", None, default="10"), "absent: the default applies"),
        ("absent-required", P("string", None, required=True), "absent and required: start fails naming the key"),
        ("absent-optional", P("string", None), "absent, optional, no default: not set"),
        ("empty-typed-is-absent", P("integer", "", default="10"), "an empty value for a typed key counts as not set"),
        ("empty-typed-required", P("duration", "", required=True), "empty and required"),
        ("empty-string-is-value", P("string", "", default="x"), "an empty string is a value"),
        ("invalid-not-default", P("integer", "ten", default="10"), "present but invalid never falls back to the default"),
        ("invalid-default", P("integer", None, default="ten"), "a broken default is a configuration error too"),
        # integers
        ("int", P("integer", "10"), "integer"), ("int-negative", P("integer", "-5"), "negative"),
        ("int-zero-padded", P("integer", "007"), "leading zeros are decimal, not octal"),
        ("int-plus", P("integer", "+5"), "no plus sign"), ("int-space", P("integer", " 5"), "no whitespace"),
        ("int-trailing-newline", P("integer", "5\n"), "a trailing newline is not trimmed"),
        ("int-underscore", P("integer", "1_000"), "no digit separators"), ("int-hex", P("integer", "0x10"), "no hex"),
        ("int-float", P("integer", "1.0"), "not an integer"), ("int-exponent", P("integer", "1e3"), "no exponent"),
        ("int-max", P("integer", "9007199254740991"), "the largest integer exact in every language (2^53-1)"),
        ("int-overflow", P("integer", "9007199254740992"), "beyond 2^53-1"),
        ("int-min", P("integer", "-9007199254740991"), "-(2^53-1)"),
        ("int-fullwidth", P("integer", "１０"), "full-width digits"),
        ("int-minimum", P("integer", "0", minimum=1), "below the declared minimum"),
        # booleans
        ("bool-true", P("boolean", "true"), "true"), ("bool-false", P("boolean", "false"), "false"),
        ("bool-one", P("boolean", "1"), "1"), ("bool-zero", P("boolean", "0"), "0"),
        ("bool-upper", P("boolean", "TRUE"), "case-sensitive"), ("bool-title", P("boolean", "True"), "case-sensitive"),
        ("bool-t", P("boolean", "t"), "single letters are not accepted"), ("bool-yes", P("boolean", "yes"), "yes/no are not booleans"),
        ("bool-on", P("boolean", "on"), "on/off are not booleans"),
        # durations (Go syntax)
        ("dur-seconds", P("duration", "5s"), "5s"), ("dur-minutes", P("duration", "15m"), "15m"),
        ("dur-compound", P("duration", "1h30m"), "compound"), ("dur-fraction", P("duration", "1.5h"), "fraction"),
        ("dur-ms", P("duration", "200ms"), "milliseconds"), ("dur-us", P("duration", "10us"), "microseconds"),
        ("dur-micro-sign", P("duration", "10µs"), "U+00B5 micro sign"), ("dur-mu", P("duration", "10μs"), "U+03BC Greek mu"),
        ("dur-ns", P("duration", "7ns"), "nanoseconds"), ("dur-zero", P("duration", "0"), "a bare 0"),
        ("dur-zero-unit", P("duration", "0s"), "0s"), ("dur-leading-dot", P("duration", ".5s"), ".5s is valid Go syntax"),
        ("dur-trailing-dot", P("duration", "5.s"), "5.s is valid Go syntax"),
        ("dur-fraction-truncates", P("duration", "1.0000000001s"), "below a nanosecond truncates"),
        ("dur-plus", P("duration", "+5s"), "a leading plus is Go syntax"),
        ("dur-negative", P("duration", "-5s"), "negative durations are rejected for configuration"),
        ("dur-bare-number", P("duration", "5"), "a number without a unit"),
        ("dur-days", P("duration", "1d"), "there is no day unit"), ("dur-upper", P("duration", "5S"), "units are lower case"),
        ("dur-space", P("duration", "5 s"), "no spaces"), ("dur-dot-only", P("duration", ".s"), "no digits"),
        ("dur-iso", P("duration", "PT5S"), "ISO 8601 is not accepted"),
        ("dur-max", P("duration", "2562047h47m16.854775807s"), "the largest Go duration"),
        ("dur-overflow", P("duration", "2562048h"), "beyond int64 nanoseconds"),
        # duration lists
        ("durlist-default-backoff", P("duration_list", "1s,10s,1m,5m,15m,30m,1h"), "EVENTS_BACKOFF default"),
        ("durlist-conformance", P("duration_list", "200ms,500ms,1s"), "the compconf tuning"),
        ("durlist-single", P("duration_list", "5s"), "one element"),
        ("durlist-space", P("duration_list", "1s, 10s"), "no spaces after commas"),
        ("durlist-empty-element", P("duration_list", "1s,,10s"), "an empty element"),
        ("durlist-trailing-comma", P("duration_list", "1s,"), "a trailing comma"),
        ("durlist-zero", P("duration_list", "0s,1s"), "backoff steps are positive"),
        # URLs
        ("url-http", P("url", "http://otel-collector:4318"), "OTLP base URL"),
        ("url-https-path", P("url", "https://authz.example.com/base/"), "https with a path"),
        ("url-nats", P("url", "nats://be-nats:4222", schemes=["nats", "postgres", "kafka"]), "EVENT_BUS_URL nats"),
        ("url-postgres-query", P("url", "postgres://be-postgres:5432/brickkit_db?schema=be_bus", schemes=["nats", "postgres", "kafka"]),
         "EVENT_BUS_URL postgres queue"),
        ("url-kafka-list", P("url", "kafka://broker1:9092,broker2:9092", schemes=["nats", "postgres", "kafka"]),
         "a broker list is not one host"),
        ("url-scheme-not-allowed", P("url", "amqp://rabbit:5672", schemes=["nats", "postgres", "kafka"]), "scheme not allowed for the key"),
        ("url-no-scheme", P("url", "be-nats:4222"), "no scheme"), ("url-relative", P("url", "/authz"), "relative"),
        ("url-upper-scheme", P("url", "HTTP://x:1"), "scheme in upper case"),
        ("url-port-range", P("url", "http://x:70000"), "port out of range"),
        ("url-space", P("url", "http://x y:1"), "whitespace"),
        ("url-ipv6", P("url", "http://[::1]:8080/"), "an IPv6 literal"),
        # JSON
        ("json-object", P("json", '{"be.cleanup":{"interval":"2s"}}', json_kind="object"), "JOBS_OVERRIDES"),
        ("json-empty-object", P("json", "{}", json_kind="object"), "an empty object"),
        ("json-array-not-object", P("json", "[]", json_kind="object"), "an array where an object is declared"),
        ("json-invalid", P("json", "{interval: 2s}", json_kind="object"), "not JSON"),
        ("json-duplicate", P("json", '{"a":1,"a":2}', json_kind="object"), "duplicate member names"),
        ("json-nan", P("json", '{"a":NaN}', json_kind="object"), "NaN is not JSON"),
        # enums
        ("enum-ok", P("enum", "warn", enum=["debug", "info", "warn", "error"]), "LOG_LEVEL"),
        ("enum-upper", P("enum", "WARN", enum=["debug", "info", "warn", "error"]), "enum values are case-sensitive"),
        ("enum-default", P("enum", None, enum=["debug", "info", "warn", "error"], default="info"), "LOG_LEVEL default"),
        # secrets: delivered as files (mount: file); the variable holds the path (P2.7, P2.12)
        ("secret-file", P("string", "/run/brickkit/secrets/erp-sales-3-0-0/PG_PASSWORD_FILE", secret=True),
         "a secret: the variable holds the path brickKit mounted, the value is in the file"),
        ("secret-file-host-path", P("string", "/home/dev/shop/.brickkit/generated/secrets/erp-sales-3-0-0/PG_PASSWORD_FILE", secret=True),
         "mode: local / debug: the absolute path of the file on the developer's machine"),
        ("secret-file-relative", P("string", "secrets/pg_password", secret=True), "the path must be absolute"),
        ("secret-file-root", P("string", "/", secret=True), "a directory is not a secret file"),
        ("secret-file-directory", P("string", "/run/brickkit/secrets/erp-sales-3-0-0/", secret=True), "a path ending in / is a directory"),
        ("secret-value-in-env", P("string", "s3cr3t", secret=True), "a secret value in the environment is refused: secrets travel only as files"),
        ("secret-at-file-retired", P("string", "@file:/run/secrets/pg_password", secret=True), "the @file: prefix of rc drafts is gone: the value is the path itself"),
        ("secret-missing", P("string", None, secret=True, required=True), "a required secret that is absent"),
        ("not-secret-path-is-text", P("string", "/etc/app/rules.json"), "for a key that is not secret a path is ordinary text"),
    ]
    for slug, inp, why in rows:
        add(c, slug, why, "parse_value", inp, parse_value, ["P2.3", "P2.7"])
    c.add("undeclared", "reading a key the component did not declare in configSchema", "read_undeclared",
          {"key": "SOME_OTHER_KEY", "declared": ["PG_HOST", "PG_SCHEMA"]}, error="CONFIG_UNDECLARED", refs=["P2.2"])
    c.add("undeclared-reserved-ok", "platform names may be read without being declared", "read_undeclared",
          {"key": "COMPONENT_ID", "declared": ["PG_HOST"]}, expected={"allowed": True}, refs=["P2.2"])
    for slug, content, req, why in [
        ("plain", "s3cr3t", True, "the file's text is the value"),
        ("trailing-lf", "s3cr3t\n", True, "one trailing LF (what an editor or echo writes) is removed"),
        ("trailing-crlf", "s3cr3t\r\n", True, "one trailing CRLF is removed"),
        ("two-lf", "s3cr3t\n\n", True, "only one trailing newline is removed"),
        ("spaces-kept", " s3cr3t ", True, "spaces are part of the value"),
        ("pem", "-----BEGIN PRIVATE KEY-----\nMC4CAQAwBQYDK2VwBCIEIA==\n-----END PRIVATE KEY-----\n", True, "a PEM keeps its inner newlines"),
        ("empty-required", "", True, "an empty file for a required secret"),
        ("newline-only-required", "\n", True, "a file holding only a newline is empty"),
        ("empty-optional", "", False, "an empty file for an optional secret: not set"),
    ]:
        add(c, "secret-text-" + slug, why, "secret_text", {"content": content, "required": req}, secret_text, ["P2.9"])
    return c


def gen_endpoints():
    c = CaseList("config", "endpoints")
    for slug, dep, port in [("http", "erp/inventory", ""), ("grpc", "erp/inventory", "grpc"),
                            ("hyphen-id", "integration/im-dingtalk", "grpc"), ("hyphen-id-http", "infra/bff-mobile", ""),
                            ("member-instance", "conformance/widget-go", "grpc"), ("hyphen-port", "conformance/peer", "admin-api"),
                            ("bad-id", "erp.inventory", "grpc"), ("bad-port", "erp/inventory", "GRPC")]:
        add(c, "name-" + slug, f"address variable of {dep} port {port or '(main)'}", "endpoint_name",
            {"dependency": dep, "port": port}, lambda i: {"name": endpoint_name(i["dependency"], i["port"])}, ["P2.6"])
    for slug, v, why in [
        ("plain", "http://erp-inventory-3-0-0:9096", "the scheme is stripped"),
        ("trailing-slash", "http://erp-inventory-3-0-0:9096/", "a trailing slash is stripped"),
        ("absent", None, "an optional dependency not installed: the variable does not exist"),
        ("empty", "", "empty is not absent: a configuration error"),
        ("no-scheme", "erp-inventory-3-0-0:9096", "brickKit always writes http://"),
        ("https", "https://erp-inventory:9096", "only http:// is injected"),
        ("no-port", "http://erp-inventory", "a port is always present"),
        ("path", "http://erp-inventory:9096/v1", "an address has no path"),
        ("shell-service", "http://be-go-core-1-1-0:9096", "in a shell the member's port on the shell's service"),
    ]:
        add(c, "value-" + slug, why, "endpoint_value", {"value": v}, lambda i: endpoint_value(i["value"]), ["P2.5", "P2.6"])
    for slug, key, v, why in [
        ("authz", "AUTHZ_URL", "http://infra-authz-3-0-0:8223", "$endpoint:infra/authz: the REST base"),
        ("authz-grpc", "AUTHZ_GRPC_URL", "http://infra-authz-3-0-0:9223", "$endpoint:infra/authz:grpc: the gRPC target is host:port"),
        ("iam", "IAM_URL", "http://infra-iam-casdoor-3-0-0:8200", "the identity family the same way"),
        ("iam-grpc", "IAM_GRPC_URL", "http://infra-iam-casdoor-3-0-0:9200", "$endpoint:infra/iam-casdoor:grpc"),
        ("grpc-port-unrelated", "AUTHZ_GRPC_URL", "http://infra-authz-openfga-3-0-0:7311", "the gRPC port is whatever the member declares: no port arithmetic"),
        ("shell-hosted", "AUTHZ_GRPC_URL", "http://be-go-infra-1-1-0:9223", "a member hosted by a shell: the shell's service, the member's own port"),
        ("trailing-slash", "AUTHZ_URL", "http://infra-authz-3-0-0:8223/", "a trailing slash is stripped"),
        ("absent", "IAM_GRPC_URL", None, "the family member does not run: the key does not exist and the caller degrades"),
        ("no-port", "AUTHZ_URL", "http://infra-authz-3-0-0", "the port must be explicit"),
        ("path", "AUTHZ_URL", "http://infra-authz-3-0-0:8223/authz/v2", "a family address has no path; REST paths are appended by the runtime"),
        ("https", "AUTHZ_URL", "https://infra-authz-3-0-0:8223", "project-network addresses are http://"),
        ("grpc-no-scheme", "AUTHZ_GRPC_URL", "infra-authz-3-0-0:9223", "the value is written by $endpoint:, always with http://"),
        ("empty", "AUTHZ_URL", "", "a family key may not be empty"),
        ("not-family-key", "AUTHZ_BUNDLE_URL", "http://infra-authz-3-0-0:8223/authz/v2/bundle", "only the four family address keys"),
    ]:
        add(c, "family-" + slug, why, "family_address", {"key": key, "value": v}, family_address, ["P2.10"])
    return c


def gen_keys():
    c = CaseList("config", "keys")
    for slug, k in [("pg-host", "PG_HOST"), ("events-backoff", "EVENTS_BACKOFF"),
                    ("number-format", "SALES_ORDER_NO_FORMAT"), ("s3-url", "S3_URL"), ("one-letter", "A"),
                    ("letter-digit", "X1"), ("component-id", "COMPONENT_ID"), ("component-version", "COMPONENT_VERSION"),
                    ("port", "PORT"), ("endpoint-suffix", "UPSTREAM_ENDPOINT"),
                    ("dependency-endpoint", "ERP_INVENTORY_GRPC_ENDPOINT"), ("served-members", "BRICKKIT_SERVED_MEMBERS"),
                    ("served-members-config", "BRICKKIT_SERVED_MEMBERS_CONFIG"), ("lower-case", "pg_host"),
                    ("hyphen", "PG-HOST"), ("leading-digit", "1PG"), ("leading-underscore", "_PG"), ("space", "PG HOST"),
                    ("empty", "")]:
        add(c, slug, f"may a component declare {k!r}?", "key_name", {"key": k}, lambda i: key_name(i["key"]), ["P2.4"])
    for slug, inp, why in [
        ("secret-file", {"key": "PG_PASSWORD_FILE", "secret": True, "mount": "file"}, "a secret key: secret, mount: file, name ending in _FILE"),
        ("plain", {"key": "PG_USER"}, "a plain key"),
        ("secret-env", {"key": "PG_PASSWORD", "secret": True}, "a secret that would travel in the environment"),
        ("secret-env-file-name", {"key": "PG_PASSWORD_FILE", "secret": True}, "the _FILE name without mount: file would carry the value, not a path"),
        ("mount-no-suffix", {"key": "SIGNING_KEY", "secret": True, "mount": "file"}, "a file-delivered key is named ..._FILE"),
        ("plain-file-suffix", {"key": "RULES_FILE"}, "_FILE is reserved for file-delivered secrets"),
        ("mount-not-secret", {"key": "RULES_FILE", "mount": "file"}, "brickKit: mount: file only together with secret: true"),
        ("mount-integer", {"key": "PORT_FILE", "secret": True, "mount": "file", "type": "integer"}, "brickKit: a mounted item is a string"),
        ("mount-unknown", {"key": "KEY_FILE", "secret": True, "mount": "volume"}, "file is the only mount"),
        ("reserved-still", {"key": "UPSTREAM_ENDPOINT", "secret": True, "mount": "file"}, "reserved names stay reserved"),
    ]:
        add(c, "decl-" + slug, why, "key_declaration", inp, key_declaration, ["P2.4", "P2.12"])
    return c


def gen_forms():
    c = CaseList("config", "forms")
    for slug, w, secret, why in [
        ("literal", "erp_sales", False, "a literal"),
        ("var", "$var:PG_HOST", False, "a shared variable"),
        ("var-secret", "$var:PG_PASSWORD", True, "a secret through a shared variable (vars.yaml holds ${PG_PASSWORD})"),
        ("var-with-suffix", "$var:PG_HOST:5432", False, "$var: must be the whole value"),
        ("env", "${PG_PASSWORD}", True, "a secret from .env or the process environment"),
        ("env-empty-default", "${DINGTALK_SECRET:-}", True, "may legitimately be empty"),
        ("env-plain-default", "${LOG_LEVEL:-info}", False, "a default for a plain value"),
        ("env-secret-default", "${PG_PASSWORD:-dev}", True, "a plaintext default for a secret"),
        ("env-nested", "${A:-${B}}", False, "references do not nest"),
        ("env-digit-name", "${1X}", False, "a name cannot start with a digit"),
        ("env-unclosed", "${PG_PASSWORD", True, "a missing brace"),
        ("template", "jdbc:postgresql://${PG_HOST}:5432/people", False, "a template inside a string"),
        ("template-secret", "postgres://u:${PG_PASSWORD}@h/db", True, "a secret written inside a template leaks the rest as plaintext"),
        ("file", "file://.secrets/app_token_private_key.pem", True, "a file read at generation time"),
        ("file-absolute", "file:///etc/passwd", True, "file:// paths are relative to the project root"),
        ("file-parent", "file://../outside.pem", True, "no escaping the project"),
        ("secret-literal", "s3cr3t", True, "a plaintext secret"),
        ("existing-secret", {"existingSecret": "pg-credentials", "key": "password"}, True, "Kubernetes: a Secret managed elsewhere"),
        ("existing-secret-plain", {"existingSecret": "pg-credentials", "key": "host"}, False, "existingSecret only for secret: true items"),
        ("existing-secret-bad", {"existingSecret": "pg-credentials"}, True, "the key is required"),
        ("endpoint", "$endpoint:infra/authz", False, "a family address: the project's default version, main port"),
        ("endpoint-port", "$endpoint:infra/authz:grpc", False, "the extra port named grpc"),
        ("endpoint-version-port", "$endpoint:infra/authz@3.0.0:grpc", False, "a given version, then the port"),
        ("endpoint-path", "$endpoint:infra/iam-casdoor/.well-known/jwks.json", False, "an address with a path appended"),
        ("endpoint-self-callback", "$endpoint:infra/iam-casdoor/api/iam/webhooks/casdoor", False, "a member's own callback address, handed to its IdP"),
        ("endpoint-version-path", "$endpoint:infra/authz@3.0.0/authz/v2/bundle", False, "a version, then a path"),
        ("endpoint-port-then-version", "$endpoint:infra/authz:grpc@3.0.0", False, "the version comes before the port"),
        ("endpoint-loose-version", "$endpoint:infra/authz@3.0", False, "versions are exact"),
        ("endpoint-port-upper", "$endpoint:infra/authz:GRPC", False, "port names are lower case"),
        ("endpoint-one-segment", "$endpoint:authz", False, "a component ID has two segments"),
        ("endpoint-suffix", "http://$endpoint:infra/authz", False, "$endpoint: must be the whole value"),
        ("endpoint-secret", "$endpoint:infra/authz", True, "an address is never a secret"),
    ]:
        add(c, slug, why, "value_form", {"written": w, "secret": secret}, value_form,
            ["P2.10"] if "$endpoint:" in str(w) else ["P2.7"])
    return c


def main():
    counts = {}
    for topic, fn in [("values", gen_values), ("endpoints", gen_endpoints), ("keys", gen_keys), ("forms", gen_forms)]:
        counts[topic] = write_file(os.path.join(OUT, f"{topic}.json"), "config", topic, GEN, fn())
    print("config", counts, "total", sum(counts.values()))


if __name__ == "__main__":
    main()
