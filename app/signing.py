"""Canonical JSON and Ed25519 signing helpers shared by the server."""
import base64
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical_bytes(payload: dict) -> bytes:
    """Sorted keys, no whitespace, UTF-8. Must match SPEC.md section 1."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def load_private_key(pem: bytes) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("signing key must be Ed25519")
    return key


def sign_payload(key: Ed25519PrivateKey, payload: dict, kid: str = "k1") -> dict:
    """Return {"kid": ..., "payload": ..., "signature": ...} as defined in SPEC.md."""
    signature = key.sign(canonical_bytes(payload))
    return {"kid": kid, "payload": payload, "signature": b64url(signature)}
