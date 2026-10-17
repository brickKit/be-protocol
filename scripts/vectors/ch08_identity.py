"""Chapter 08: user access token verification (P8.1, P8.3).

The keys are test-only: an Ed25519 key from a fixed seed, a P-256 key from a fixed scalar, and the RSA key in
jwt-test-rsa.pem, generated once for these vectors and used nowhere else. ECDSA signatures are deterministic
(RFC 6979), so the vectors are byte-stable.
"""
import base64
import hashlib
import json
import pathlib

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from common import write

HERE = pathlib.Path(__file__).resolve().parent
ISSUER = "https://iam.example.test/"
AUDIENCE = "be:deployment:0190f3a1-0000-7000-8000-00000000d001"
SUBJECT = "0190f3a1-0000-7000-8000-0000000000a1"
NOW = 1792200000  # 2026-10-17T01:20:00Z, seconds
SKEW = 60


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64int(n, size):
    return b64(n.to_bytes(size, "big"))


RSA = serialization.load_pem_private_key((HERE / "jwt-test-rsa.pem").read_bytes(), password=None)
EC = ec.derive_private_key(int.from_bytes(hashlib.sha256(b"be-protocol jwt test ec").digest(), "big") % (2 ** 255), ec.SECP256R1())
ED = ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"be-protocol jwt test ed").digest())
OTHER_ED = ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"be-protocol jwt other ed").digest())


def jwks():
    rn = RSA.public_key().public_numbers()
    en = EC.public_key().public_numbers()
    ed_pub = ED.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {"keys": [
        {"kty": "RSA", "kid": "rsa-1", "use": "sig", "alg": "RS256", "n": b64int(rn.n, 256), "e": b64int(rn.e, 3)},
        {"kty": "EC", "kid": "ec-1", "use": "sig", "alg": "ES256", "crv": "P-256", "x": b64int(en.x, 32), "y": b64int(en.y, 32)},
        {"kty": "OKP", "kid": "ed-1", "use": "sig", "alg": "EdDSA", "crv": "Ed25519", "x": b64(ed_pub)},
    ]}


def sign(alg, key, data):
    if alg == "RS256":
        return key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    if alg == "ES256":
        r, s = decode_dss_signature(key.sign(data, ec.ECDSA(hashes.SHA256(), deterministic_signing=True)))
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")
    if alg == "EdDSA":
        return key.sign(data)
    raise ValueError(alg)


KEYS = {"RS256": ("rsa-1", RSA), "ES256": ("ec-1", EC), "EdDSA": ("ed-1", ED)}


def claims(**over):
    c = {"iss": ISSUER, "aud": AUDIENCE, "sub": SUBJECT, "iat": NOW - 30, "exp": NOW + 600, "jti": "t1"}
    for k, v in over.items():
        if v is None:
            c.pop(k, None)
        else:
            c[k] = v
    return c


def token(alg="EdDSA", header=None, body=None, key=None, kid=None, raw_sig=None):
    h = {"alg": alg, "typ": "at+jwt", "kid": kid or KEYS.get(alg, ("ed-1",))[0]}
    for k, v in (header or {}).items():
        if v is None:
            h.pop(k, None)
        else:
            h[k] = v
    signing = (b64(json.dumps(h, separators=(",", ":")).encode()) + "." +
               b64(json.dumps(body if body is not None else claims(), separators=(",", ":")).encode())).encode()
    if raw_sig is not None:
        sig = raw_sig
    else:
        sig = sign(alg, key or KEYS[alg][1], signing)
    return signing.decode() + "." + b64(sig)


def jwt_vectors():
    import hmac
    rsa_pub_pem = RSA.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    hs_signing = (b64(json.dumps({"alg": "HS256", "typ": "at+jwt", "kid": "rsa-1"}, separators=(",", ":")).encode()) + "." +
                  b64(json.dumps(claims(), separators=(",", ":")).encode())).encode()
    hs = hs_signing.decode() + "." + b64(hmac.new(rsa_pub_pem, hs_signing, hashlib.sha256).digest())
    good = token("EdDSA")
    head, payload, sig = good.split(".")
    tampered = head + "." + b64(json.dumps(claims(sub="0190f3a1-0000-7000-8000-0000000000a2"), separators=(",", ":")).encode()) + "." + sig
    cases = [
        ("valid-rs256", token("RS256"), None),
        ("valid-es256", token("ES256"), None),
        ("valid-eddsa", good, None),
        ("audience-in-array", token(body=claims(aud=["other", AUDIENCE])), None),
        ("roles-claim-ignored", token(body=claims(roles=["admin"], dept="org1")), None),
        ("expired-within-skew", token(body=claims(exp=NOW - 30)), None),
        ("expired", token(body=claims(exp=NOW - 61)), "exp"),
        ("no-exp", token(body=claims(exp=None)), "exp"),
        ("not-yet-valid", token(body=claims(nbf=NOW + 61)), "nbf"),
        ("issued-in-the-future", token(body=claims(iat=NOW + 61)), "iat"),
        ("alg-none", token(header={"alg": "none"}, raw_sig=b""), "alg"),
        ("hs256-with-public-key", hs, "alg"),
        ("alg-does-not-match-key", token("EdDSA", kid="ec-1", key=ED), "alg"),
        ("typ-jwt", token(header={"typ": "JWT"}), "typ"),
        ("typ-missing", token(header={"typ": None}), "typ"),
        ("kid-missing", token(header={"kid": None}), "kid"),
        ("kid-unknown", token(kid="ed-9"), "kid_unknown"),
        ("wrong-issuer", token(body=claims(iss="https://evil.example.test/")), "iss"),
        ("wrong-audience", token(body=claims(aud="be:deployment:other")), "aud"),
        ("no-audience", token(body=claims(aud=None)), "aud"),
        ("subject-not-uuid", token(body=claims(sub="alice@example.test")), "sub"),
        ("subject-upper-case", token(body=claims(sub=SUBJECT.upper())), "sub"),
        ("tampered-payload", tampered, "signature"),
        ("signed-by-another-key", token("EdDSA", key=OTHER_ED), "signature"),
        ("two-parts", head + "." + payload, "format"),
    ]
    write("jwt-verify", ["P8.1", "P8.3"],
          "用户访问凭据的核验。jwks 是签发方公布的公钥（第一项 kind=keys），now 是核验时刻（UNIX 秒），容许 60 秒时钟偏差；其余各项是"
          "一个凭据与期望：problem 为空表示合格，否则是第一个不合格的检查（format、alg、typ、kid、kid_unknown、signature、iss、aud、exp、"
          "nbf、iat、sub），对外一律答 TOKEN_INVALID。kid_unknown 表示刷新公钥之后仍不认识。每个用例只有一处缺陷。密钥只用于这些向量。",
          [{"id": "keys", "kind": "keys", "jwks": jwks(), "issuer": ISSUER, "audience": AUDIENCE, "now": NOW,
            "skew_seconds": SKEW}] +
          [{"id": cid, "kind": "token", "token": t, "expect": {"valid": p is None, "problem": p or ""}} for cid, t, p in cases],
          {"jwks、issuer、audience、now": "keys 项", "token": "凭据", "expect": "valid 与第一个不合格的检查"})
