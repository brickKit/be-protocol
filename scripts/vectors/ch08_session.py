"""Chapter 08: token staleness at admission (P8.25)."""
from common import write


def stale(token_sv, entry):
    """The reference: the view's version of the subject (0 when absent) above the token's."""
    return (entry or {}).get("security_version", 0) > token_sv


def token_stale_vectors():
    cases = [
        ("equal", 3, {"security_version": 3}),
        ("token-newer", 4, {"security_version": 3}),
        ("view-newer", 3, {"security_version": 4}),
        ("view-much-newer", 1, {"security_version": 2 ** 40}),
        ("subject-absent", 1, None),
        ("field-absent", 1, {}),
    ]
    write("token-stale", ["P8.25"],
          "准入时的令牌陈旧判断。token_sv 是凭据的 be_sv；entry 是判定所用的视图分片里这个主体的条目（null 表示分片里没有这个主体，"
          "{} 表示条目没有 security_version 字段，二者都按 0）；stale 为真时答 TOKEN_STALE。",
          [{"id": cid, "token_sv": sv, "entry": e, "expect": {"stale": stale(sv, e)}} for cid, sv, e in cases],
          {"token_sv": "凭据的 be_sv", "entry": "视图分片里的主体条目", "expect": "stale"})
