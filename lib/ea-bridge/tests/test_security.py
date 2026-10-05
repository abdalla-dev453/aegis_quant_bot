import hashlib
import hmac
import time

from app.security import (
    canonical_ea_request,
    sha256_hex,
    sign_ea_request,
)


def test_sha256_hex() -> None:
    digest = sha256_hex("test_secret")
    assert digest == hashlib.sha256(b"test_secret").hexdigest()
    assert len(digest) == 64


def test_canonical_ea_request_and_signing() -> None:
    token = "abcdef0123456789abcdef0123456789"
    method = "POST"
    path = "/ea/v1/heartbeat"
    timestamp = str(int(time.time()))
    nonce = "a1b2c3d4e5f6g7h8"
    body = b'{"balance": "10000.00"}'

    expected_canonical = f"{method}\n{path}\n{timestamp}\n{nonce}\n{sha256_hex('{\"balance\": \"10000.00\"}')}".encode()
    assert canonical_ea_request(method, path, timestamp, nonce, body) == expected_canonical

    signature = sign_ea_request(token, method, path, timestamp, nonce, body)
    assert len(signature) == 64
    assert hmac.compare_digest(
        signature,
        hmac.new(token.encode("ascii"), expected_canonical, hashlib.sha256).hexdigest(),
    )


def test_tampered_payload_signature_mismatch() -> None:
    token = "abcdef0123456789abcdef0123456789"
    method = "POST"
    path = "/ea/v1/heartbeat"
    timestamp = str(int(time.time()))
    nonce = "a1b2c3d4e5f6g7h8"
    body = b'{"balance": "10000.00"}'

    sig1 = sign_ea_request(token, method, path, timestamp, nonce, body)
    tampered_body = b'{"balance": "99999.00"}'
    sig2 = sign_ea_request(token, method, path, timestamp, nonce, tampered_body)

    assert sig1 != sig2
