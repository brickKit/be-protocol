"""Chapter 11: what the edge does with one browser request (P11.1-P11.4, P11.7)."""
from common import write

B_REPLAY = 1 << 20
CHANGING = {"POST", "PUT", "PATCH", "DELETE"}


def edge(c):
    """The reference model: the browser's result, how often the component was called, how often the edge exchanged
    and with which renew_idle."""
    out = {"forwarded": 0, "exchanges": 0, "renew_idle": None}
    answers, exchanges = list(c["answers"]), list(c["exchange"])

    def forward():
        out["forwarded"] += 1
        return answers.pop(0)

    def exchange():
        out["exchanges"] += 1
        out["renew_idle"] = c["headers"].get("BE-Polling") != "1"
        return exchanges.pop(0)

    def result(r):
        out["browser"] = r
        return out

    if not c["cookie"]:
        return result(forward())
    if c["method"] in CHANGING and c["headers"].get("BE-Request") != "1":
        return result("CSRF_HEADER_REQUIRED")
    if c["cache"] == "miss":
        e = exchange()
        if e != "ok":
            return result("SESSION_ENDED" if e == "ended" else "DEPENDENCY_UNAVAILABLE")
    a = forward()
    if a != "TOKEN_STALE":
        return result(a)
    e = exchange()
    if e != "ok":
        return result("SESSION_ENDED" if e == "ended" else "DEPENDENCY_UNAVAILABLE")
    if c["body_bytes"] > B_REPLAY:
        return result("AUTHORIZATION_UNPROVABLE")
    b = forward()
    return result("SESSION_ENDED" if b == "TOKEN_STALE" else b)


def case(cid, method="GET", cookie=True, headers=None, body=0, cache="hit", exchange=(), answers=("200",)):
    c = {"id": cid, "method": method, "cookie": cookie, "headers": headers or {}, "body_bytes": body, "cache": cache,
         "exchange": list(exchange), "answers": list(answers)}
    c["expect"] = edge(c)
    return c


def edge_flow_vectors():
    h = {"BE-Request": "1"}
    cases = [
        case("hit"),
        case("miss-exchanges", cache="miss", exchange=["ok"]),
        case("miss-polling-does-not-renew", cache="miss", headers={"BE-Polling": "1"}, exchange=["ok"]),
        case("miss-session-ended", cache="miss", exchange=["ended"], answers=[]),
        case("miss-identity-unavailable", cache="miss", exchange=["unavailable"], answers=[]),
        case("no-cookie-post-is-forwarded", method="POST", cookie=False, body=300),
        case("post-without-header", method="POST", body=300, answers=[]),
        case("delete-without-header", method="DELETE", answers=[]),
        case("get-without-header", headers={}),
        case("post-with-header", method="POST", headers=h, body=300, answers=["201"]),
        case("patch-with-header", method="PATCH", headers=h, body=300),
        case("stale-then-success", method="POST", headers=h, body=1000, exchange=["ok"], answers=["TOKEN_STALE", "201"]),
        case("stale-twice", method="POST", headers=h, body=1000, exchange=["ok"], answers=["TOKEN_STALE", "TOKEN_STALE"]),
        case("stale-then-403", method="POST", headers=h, body=1000, exchange=["ok"], answers=["TOKEN_STALE", "403"]),
        case("stale-then-409", method="PUT", headers=h, body=1000, exchange=["ok"], answers=["TOKEN_STALE", "409"]),
        case("stale-then-500", headers={}, exchange=["ok"], answers=["TOKEN_STALE", "500"]),
        case("stale-session-ended", exchange=["ended"], answers=["TOKEN_STALE"]),
        case("stale-identity-unavailable", exchange=["unavailable"], answers=["TOKEN_STALE"]),
        case("stale-body-at-the-limit", method="POST", headers=h, body=B_REPLAY, exchange=["ok"],
             answers=["TOKEN_STALE", "201"]),
        case("stale-body-over-the-limit", method="POST", headers=h, body=B_REPLAY + 1, exchange=["ok"],
             answers=["TOKEN_STALE"]),
        case("miss-then-stale", cache="miss", exchange=["ok", "ok"], answers=["TOKEN_STALE", "200"]),
        case("500-is-not-retried", answers=["500"]),
        case("timeout-is-not-retried", method="POST", headers=h, body=10, answers=["timeout"]),
    ]
    write("edge-flow", ["P11.1", "P11.2", "P11.3", "P11.4", "P11.7"],
          "边缘对一个浏览器请求的处理。method、cookie（是否带会话 Cookie）、headers（只列 BE-Request 与 BE-Polling）、body_bytes、"
          "cache（这个会话的令牌在缓存里：hit，或 miss）；exchange 是边缘依次调 Exchange 得到的回答（ok、ended 即 SESSION_ENDED、"
          "unavailable 即不可达或可重试的错误），answers 是组件依次的回答（状态码、TOKEN_STALE 或 timeout）。expect：browser 是浏览器"
          "得到的（组件的回答原样，或边缘自己答的原因），forwarded 是组件收到几次，exchanges 是换取几次，renew_idle 是换取时的取值"
          "（没有换取为 null）。B_replay = 1 MiB。",
          cases,
          {"method、cookie、headers、body_bytes、cache": "请求与缓存", "exchange": "Exchange 的回答序列",
           "answers": "组件的回答序列", "expect": "browser、forwarded、exchanges、renew_idle"})
