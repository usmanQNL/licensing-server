"""issuer_url and the license cache file (SPEC.md sections 1 and 5), end to end against the real server.

Run from the repo root: pytest
"""
import json
import os
import pathlib
import socket
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "verifiers" / "python"))
import licensing as L  # noqa: E402
from app.signing import sign_payload  # noqa: E402


# ---- cache location -------------------------------------------------------------------------

def test_cache_env_var_name():
    assert L.license_cache_env_var("QuellDAP") == "QUELLDAP_LICENSE_CACHE"
    assert L.license_cache_env_var("3d tool") == "APP_3D_TOOL_LICENSE_CACHE"


def test_default_cache_file_sits_next_to_the_license():
    assert L.default_cache_file("/a/license.json") == os.path.abspath("/a/license.cache.json")
    assert L.default_cache_file("/a/LIC-1.license.json") == os.path.abspath("/a/LIC-1.license.cache.json")
    assert L.default_cache_file("/a/lic") == os.path.abspath("/a/lic.cache.json")


def test_find_license_cache_order(tmp_path, monkeypatch):
    for var in ("QUELLDAP_LICENSE_FILE", "QUELLDAP_LICENSE_CACHE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    # Nothing set: next to ./license.json.
    assert L.find_license_cache("QuellDAP", str(tmp_path)) == str(tmp_path / "license.cache.json")
    # Only the license file is set: next to it.
    lic = tmp_path / "licensing" / "q.license.json"
    (tmp_path / ".env").write_text(f"QUELLDAP_LICENSE_FILE={lic}\n", encoding="utf-8")
    assert L.find_license_cache("QuellDAP", str(tmp_path)) == str(tmp_path / "licensing" / "q.license.cache.json")
    # The cache variable wins, relative to the project root.
    (tmp_path / ".env").write_text(f"QUELLDAP_LICENSE_FILE={lic}\nQUELLDAP_LICENSE_CACHE=cache/lic.json\n",
                                   encoding="utf-8")
    assert L.find_license_cache("QuellDAP", str(tmp_path)) == str(tmp_path / "cache" / "lic.json")
    # A real environment variable wins over .env.
    monkeypatch.setenv("QUELLDAP_LICENSE_CACHE", str(tmp_path / "env.cache.json"))
    assert L.find_license_cache("QuellDAP", str(tmp_path)) == str(tmp_path / "env.cache.json")


def test_valid_issuer_url():
    assert L.valid_issuer_url("https://licensing.example.com")
    assert L.valid_issuer_url("http://localhost:8080")
    assert L.valid_issuer_url("http://127.0.0.1:9000")
    assert not L.valid_issuer_url("http://licensing.example.com")
    assert not L.valid_issuer_url("ftp://x")
    assert not L.valid_issuer_url("")
    assert not L.valid_issuer_url(None)


# ---- a real server on a free port ------------------------------------------------------------

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def server(tmp_path, monkeypatch):
    import importlib

    import uvicorn

    key = Ed25519PrivateKey.generate()
    key_file = tmp_path / "key.pem"
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    pub = key.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    data = tmp_path / "data.json"
    data.write_text(json.dumps({"licenses": {
        "LIC-NEW": {"status": "active", "plan": "subscription", "customer": "a", "max_installs": 1},
        "LIC-OLD": {"status": "active", "plan": "subscription", "customer": "b", "max_installs": 1},
    }, "installs": {}}))
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    monkeypatch.setenv("LICENSE_STORAGE", "json")
    monkeypatch.setenv("LICENSE_JSON_PATH", str(data))
    monkeypatch.setenv("LICENSE_SIGNING_KEY_PATH", str(key_file))
    monkeypatch.setenv("LICENSE_ISSUER_URL", url + "/")  # the server strips the trailing slash
    import app.main as main
    importlib.reload(main)

    srv = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)

    def license_text(license_id, issuer_url=None):
        payload = {"v": 1, "license_id": license_id, "customer": "x", "plan": "subscription", "features": [],
                   "max_installs": 1, "issued_at": "2026-11-01T00:00:00Z", "expires_at": "2099-01-01T00:00:00Z"}
        if issuer_url:
            payload["issuer_url"] = issuer_url
        return json.dumps(sign_payload(key, payload))

    def set_status(license_id, status):
        doc = json.loads(data.read_text())
        doc["licenses"][license_id]["status"] = status
        data.write_text(json.dumps(doc))

    yield {"url": url, "pub": pub, "license": license_text, "set_status": set_status, "main": main}
    srv.should_exit = True
    thread.join(timeout=5)


def _evaluate(lic, pub, status):
    return L.evaluate(lic, pub, "subscription", json.loads(lic)["payload"]["license_id"],
                      reply_text=status.reply_text, last_seen=status.last_seen)


def test_refresh_uses_issuer_url_and_fills_the_cache(server, tmp_path):
    lic = server["license"]("LIC-NEW", server["url"])
    cache = tmp_path / "app" / "license.cache.json"
    s = L.refresh_online_status(lic, server["pub"], str(cache), endpoint="https://unused.example.com")
    assert s.contacted and s.issuer_url == server["url"], s.reason
    reply = json.loads(s.reply_text)["payload"]
    assert reply["issuer_url"] == server["url"]  # signed into the reply
    state = json.loads(cache.read_text())
    assert state["issuer_url"] == server["url"] and state["license_id"] == "LIC-NEW"
    assert state["install_hash"] and state["install_token"] and state["reply"] == s.reply_text
    assert state["last_seen"] and state["checked_at"]
    assert _evaluate(lic, server["pub"], s).valid_for_paid_features

    # Within a day: no call, cached reply used.
    again = L.refresh_online_status(lic, server["pub"], str(cache))
    assert not again.contacted and again.reply_text == s.reply_text
    # Forced: the stored install_token is sent, so the known install is accepted (no HTTP 403).
    forced = L.refresh_online_status(lic, server["pub"], str(cache), min_interval=timedelta(0))
    assert forced.contacted, forced.reason
    assert json.loads(cache.read_text())["install_hash"] == state["install_hash"]


def test_revoke_lands_at_next_check_and_offline_uses_cache(server, tmp_path):
    lic = server["license"]("LIC-NEW", server["url"])
    cache = str(tmp_path / "c.json")
    assert L.refresh_online_status(lic, server["pub"], cache).contacted
    server["set_status"]("LIC-NEW", "revoked")
    s = L.refresh_online_status(lic, server["pub"], cache, min_interval=timedelta(0))
    assert s.contacted
    result = _evaluate(lic, server["pub"], s)
    assert not result.valid_for_paid_features and "revoked" in result.reason


def test_offline_falls_back_to_cached_reply(server, tmp_path):
    lic = server["license"]("LIC-NEW", server["url"])
    cache = str(tmp_path / "c.json")
    first = L.refresh_online_status(lic, server["pub"], cache)
    # Point the same license id at a server that isn't there, through an old-style license.
    old = server["license"]("LIC-NEW")
    state = json.loads(open(cache).read())
    state["issuer_url"] = "http://127.0.0.1:1"
    open(cache, "w").write(json.dumps(state))
    s = L.refresh_online_status(old, server["pub"], cache, endpoint="http://127.0.0.1:1",
                                min_interval=timedelta(0), timeout=1)
    assert not s.contacted and "unreachable" in s.reason
    assert s.reply_text == first.reply_text  # cached reply still used
    assert _evaluate(old, server["pub"], s).valid_for_paid_features


def test_old_license_without_issuer_uses_endpoint(server, tmp_path):
    lic = server["license"]("LIC-OLD")
    s = L.refresh_online_status(lic, server["pub"], str(tmp_path / "c.json"), endpoint=server["url"] + "/")
    assert s.contacted and s.issuer_url == server["url"], s.reason
    assert _evaluate(lic, server["pub"], s).valid_for_paid_features
    # No issuer_url and no endpoint: offline only, nothing sent, the license alone decides.
    s = L.refresh_online_status(lic, server["pub"], str(tmp_path / "d.json"))
    assert not s.contacted and s.reply_text is None
    assert _evaluate(lic, server["pub"], s).valid_for_paid_features


def test_reply_from_another_issuer_is_rejected(server, tmp_path, monkeypatch):
    lic = server["license"]("LIC-NEW", server["url"])
    monkeypatch.setattr(server["main"], "ISSUER_URL", "https://other.example.com")
    s = L.refresh_online_status(lic, server["pub"], str(tmp_path / "c.json"))
    assert not s.contacted and "different issuer" in s.reason
    assert s.reply_text is None


def test_cache_for_another_license_starts_fresh(server, tmp_path):
    cache = str(tmp_path / "c.json")
    L.refresh_online_status(server["license"]("LIC-NEW", server["url"]), server["pub"], cache)
    first = json.loads(open(cache).read())
    first["keylist"] = "kept"
    open(cache, "w").write(json.dumps(first))
    L.refresh_online_status(server["license"]("LIC-OLD", server["url"]), server["pub"], cache)
    second = json.loads(open(cache).read())
    assert second["license_id"] == "LIC-OLD" and second["install_hash"] != first["install_hash"]
    assert second["keylist"] == "kept"


def test_damaged_cache_is_treated_as_empty(server, tmp_path):
    cache = tmp_path / "c.json"
    cache.write_text("{not json")
    s = L.refresh_online_status(server["license"]("LIC-NEW", server["url"]), server["pub"], str(cache))
    assert s.contacted and json.loads(cache.read_text())["install_token"]


def test_last_seen_never_moves_back(server, tmp_path):
    lic = server["license"]("LIC-NEW", server["url"])
    cache = str(tmp_path / "c.json")
    later = datetime.now(timezone.utc) + timedelta(days=2)
    L.refresh_online_status(lic, server["pub"], cache, now=later)
    s = L.refresh_online_status(lic, server["pub"], cache)  # clock now 2 days behind
    assert s.last_seen.strftime("%Y-%m-%dT%H:%M:%SZ") == later.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert not _evaluate(lic, server["pub"], s).valid_for_paid_features  # clock guard


def test_issuer_url_appears_in_replies_only_when_configured(server, monkeypatch):
    from fastapi.testclient import TestClient
    client = TestClient(server["main"].app)
    body = {"license_id": "LIC-OLD", "install_hash": "install-ZZZZZZ"}
    assert client.post("/v1/check", json=body).json()["payload"]["issuer_url"] == server["url"]
    monkeypatch.setattr(server["main"], "ISSUER_URL", "")
    body["install_hash"] = "install-YYYYYY"
    assert "issuer_url" not in client.post("/v1/check", json=body).json()["payload"]
