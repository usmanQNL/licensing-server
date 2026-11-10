"""Server tests: status, seat limits, and signed replies (run from the repo root: pytest)."""
import base64
import json
import os
import pathlib
import sys
import tempfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    key_file = tmp_path / "key.pem"
    key_file.write_bytes(pem)
    data = tmp_path / "data.json"
    data.write_text(json.dumps({
        "licenses": {
            "ACTIVE": {"status": "active", "plan": "full", "customer": "a", "max_installs": 2},
            "REVOKED": {"status": "revoked", "plan": "full", "customer": "b"},
        },
        "installs": {},
    }))
    monkeypatch.setenv("LICENSE_STORAGE", "json")
    monkeypatch.setenv("LICENSE_JSON_PATH", str(data))
    monkeypatch.setenv("LICENSE_SIGNING_KEY_PATH", str(key_file))
    import importlib
    import app.main as main
    importlib.reload(main)
    from fastapi.testclient import TestClient
    return TestClient(main.app), key.public_key()


def check(client, lid, install="install-000001"):
    return client.post("/v1/check", json={"license_id": lid, "install_hash": install}).json()


def test_active_license_is_signed(client):
    c, pub = client
    body = check(c, "ACTIVE")
    assert body["payload"]["status"] == "active"
    sig = base64.urlsafe_b64decode(body["signature"] + "=" * (-len(body["signature"]) % 4))
    from app.signing import canonical_bytes
    pub.verify(sig, canonical_bytes(body["payload"]))  # raises if the signature is wrong


def test_unknown_and_revoked(client):
    c, _ = client
    assert check(c, "NOPE")["payload"]["status"] == "unknown"
    assert check(c, "REVOKED")["payload"]["status"] == "revoked"


def test_seat_limit(client):
    c, _ = client
    first = check(c, "ACTIVE", "install-AAAAAA")
    assert first["payload"]["status"] == "active"
    token = first["payload"]["install_token"]
    assert check(c, "ACTIVE", "install-BBBBBB")["payload"]["status"] == "active"
    assert check(c, "ACTIVE", "install-CCCCCC")["payload"]["status"] == "limit_reached"
    # The install that holds a seat is still allowed, with its token.
    again = c.post("/v1/check", json={"license_id": "ACTIVE", "install_hash": "install-AAAAAA",
                                      "install_token": token}).json()
    assert again["payload"]["status"] == "active"


def test_install_token_required(client):
    c, _ = client
    token = check(c, "ACTIVE", "install-DDDDDD")["payload"]["install_token"]
    # Without the token, or with a wrong one, a known install is refused.
    no_token = c.post("/v1/check", json={"license_id": "ACTIVE", "install_hash": "install-DDDDDD"})
    assert no_token.status_code == 403
    wrong = c.post("/v1/check", json={"license_id": "ACTIVE", "install_hash": "install-DDDDDD",
                                      "install_token": "forged"})
    assert wrong.status_code == 403
    ok = c.post("/v1/check", json={"license_id": "ACTIVE", "install_hash": "install-DDDDDD",
                                   "install_token": token})
    assert ok.status_code == 200


def test_rate_limit_returns_429(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    key_file = tmp_path / "key.pem"
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                           serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    data = tmp_path / "data.json"
    data.write_text(json.dumps({"licenses": {"A": {"status": "active", "plan": "full", "customer": "x"}},
                                "installs": {}}))
    monkeypatch.setenv("LICENSE_STORAGE", "json")
    monkeypatch.setenv("LICENSE_JSON_PATH", str(data))
    monkeypatch.setenv("LICENSE_SIGNING_KEY_PATH", str(key_file))
    monkeypatch.setenv("LICENSE_RATE_LIMIT_PER_MIN", "3")
    import importlib
    import app.main as main
    importlib.reload(main)
    from fastapi.testclient import TestClient
    c = TestClient(main.app)
    codes = [c.post("/v1/check", json={"license_id": "A", "install_hash": f"install-{i:04d}"}).status_code
             for i in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_oversized_body_rejected(client):
    c, _ = client
    r = c.post("/v1/check", content=b"x" * 5000, headers={"content-type": "application/json"})
    assert r.status_code == 413
