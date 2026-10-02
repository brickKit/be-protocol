#!/usr/bin/env python3
"""Generate vectors/config/*.json (protocol P2; foundations 24; brickKit's
environment-variable contract).

values.json   how a component parses the value of one declared key at start
endpoints.json  dependency address variables (names and values)
keys.json     which key names a component may declare
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
    res = {"set": True, "value": out}
    if inp.get("secret"):
        if v.startswith("@file:"):
            path = v[len("@file:"):]
            if not path.startswith("/") or "\x00" in path or path == "/":
                raise CfgError("CONFIG_INVALID")
            res = {"set": True, "source": "file", "path": path}
        else:
            res = {"set": True, "source": "env", "value": out}
    return res


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


def family_url(v):
    # P2.10: a slot family's *_URL is http://<host>:<port> with no path; its gRPC target is host:(port + 1000)
    if not isinstance(v, str) or not v.startswith("http://"):
        raise CfgError("CONFIG_INVALID")
    rest = v[len("http://"):].rstrip("/")
    m = re.fullmatch(r"([a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*):([0-9]{1,5})", rest)
    if not m or not 1 <= int(m.group(5)) <= 65535 - 1000:
        raise CfgError("CONFIG_INVALID")
    return {"base": "http://" + rest, "grpc_target": f"{m.group(1)}:{int(m.group(5)) + 1000}"}


RESERVED = {"COMPONENT_ID", "COMPONENT_VERSION", "PORT"}


def key_name(k):
    if not isinstance(k, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", k):
        raise CfgError("CONFIG_KEY_INVALID")
    if k in RESERVED or k.endswith("_ENDPOINT") or k.startswith("BRICKKIT_SERVED_MEMBERS"):
        raise CfgError("CONFIG_KEY_RESERVED")
    return {"valid": True}


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
    if "${" in rest or "$var:" in w:
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
        # secrets
        ("secret-env", P("string", "s3cr3t", secret=True), "a secret from the environment"),
        ("secret-file", P("string", "@file:/run/secrets/pg_password", secret=True), "a runtime file reference: re-read when it changes"),
        ("secret-file-relative", P("string", "@file:secrets/pg_password", secret=True), "the file path must be absolute"),
        ("secret-file-root", P("string", "@file:/", secret=True), "a directory is not a secret file"),
        ("not-secret-file-literal", P("string", "@file:/run/secrets/x"), "@file: is only special for secret: true keys"),
        ("secret-missing", P("string", None, secret=True, required=True), "a required secret that is absent"),
    ]
    for slug, inp, why in rows:
        add(c, slug, why, "parse_value", inp, parse_value, ["P2.3", "P2.7"])
    c.add("undeclared", "reading a key the component did not declare in configSchema", "read_undeclared",
          {"key": "SOME_OTHER_KEY", "declared": ["PG_HOST", "PG_SCHEMA"]}, error="CONFIG_UNDECLARED", refs=["P2.2"])
    c.add("undeclared-reserved-ok", "platform names may be read without being declared", "read_undeclared",
          {"key": "COMPONENT_ID", "declared": ["PG_HOST"]}, expected={"allowed": True}, refs=["P2.2"])
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
    for slug, v, why in [
        ("authz", "http://infra-authz-3-0-0:8223", "REST base kept, gRPC target on port + 1000"),
        ("iam", "http://infra-iam-casdoor-3-0-0:8200", "the identity family the same way"),
        ("trailing-slash", "http://infra-authz-3-0-0:8223/", "a trailing slash is stripped"),
        ("no-port", "http://infra-authz-3-0-0", "the port must be explicit"),
        ("path", "http://infra-authz-3-0-0:8223/authz/v2", "a family URL has no path"),
        ("https", "https://infra-authz-3-0-0:8223", "project-network addresses are http://"),
        ("port-overflow", "http://infra-authz-3-0-0:64600", "port + 1000 above 65535"),
        ("empty", "", "a required family key may not be empty"),
    ]:
        add(c, "family-" + slug, why, "family_url", {"value": v}, lambda i: family_url(i["value"]), ["P2.10"])
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
    ]:
        add(c, slug, why, "value_form", {"written": w, "secret": secret}, value_form, ["P2.7"])
    return c


def main():
    counts = {}
    for topic, fn in [("values", gen_values), ("endpoints", gen_endpoints), ("keys", gen_keys), ("forms", gen_forms)]:
        counts[topic] = write_file(os.path.join(OUT, f"{topic}.json"), "config", topic, GEN, fn())
    print("config", counts, "total", sum(counts.values()))


if __name__ == "__main__":
    main()
