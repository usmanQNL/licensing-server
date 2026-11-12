import json, base64, sys, threading, http.server, os, tempfile
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "verifiers" / "python"))
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey as K
import licensing as L

def pem_pub(k): return k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
def test_key_list_verify_cache_and_rollback():
    root = K.generate(); signer = K.generate()
    def make_list(keys, revoked, issued):
        payload = {"v": 1, "issued_at": issued, "keys": keys, "revoked": revoked}
        sig = root.sign(L._canonical(payload))
        return json.dumps({"kid": "root", "payload": payload, "signature": base64.urlsafe_b64encode(sig).rstrip(b"=").decode()})
    root_pem = pem_pub(root)
    good = make_list({"k1": pem_pub(signer), "k0": pem_pub(K.generate())}, ["k0"], "2026-11-10T08:00:00Z")
    assert set(L.verify_key_list(good, root_pem)) == {"k1"}
    # wrong signer
    bad = json.loads(good); bad["payload"]["keys"]["k9"] = pem_pub(K.generate())
    try: L.verify_key_list(json.dumps(bad), root_pem); raise AssertionError("tampered list accepted")
    except ValueError: pass
    other = K.generate()
    try: L.verify_key_list(good, pem_pub(other)); raise AssertionError("wrong root accepted")
    except ValueError: pass

    # server + cache behaviour
    body = {"text": good}
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(body["text"].encode())
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    d = tempfile.mkdtemp(); cache = os.path.join(d, "keys.json")
    assert set(L.load_trusted_keys(root_pem, cache, url)) == {"k1"} and os.path.exists(cache)
    # older list must not roll back a revocation
    body["text"] = make_list({"k1": pem_pub(signer), "k0": pem_pub(K.generate())}, [], "2026-11-01T00:00:00Z")
    assert set(L.load_trusted_keys(root_pem, cache, url)) == {"k1"}, "rollback accepted"
    # newer list applies
    body["text"] = make_list({"k2": pem_pub(K.generate())}, ["k1"], "2026-11-11T00:00:00Z")
    assert set(L.load_trusted_keys(root_pem, cache, url)) == {"k2"}
    # server down: uses cache
    srv.shutdown(); srv.server_close()
    assert set(L.load_trusted_keys(root_pem, cache, url, timeout=1)) == {"k2"}
    # nothing cached and no server
    try: L.load_trusted_keys(root_pem, os.path.join(d, "none.json"), url, timeout=1); raise AssertionError("no error")
    except ValueError: pass


def test_old_key_list_only_cache_file_is_still_read(tmp_path):
    import json
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    root = Ed25519PrivateKey.generate()
    root_pem = root.public_key().public_bytes(serialization.Encoding.PEM,
                                              serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    payload = {"v": 1, "issued_at": "2026-11-01T00:00:00Z", "keys": {"k1": "PEM"}, "revoked": []}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = base64.urlsafe_b64encode(root.sign(canonical)).rstrip(b"=").decode()
    old = tmp_path / "keys-cache.json"
    old.write_text(json.dumps({"kid": "root", "payload": payload, "signature": sig}))
    assert L.load_trusted_keys(root_pem, str(old)) == {"k1": "PEM"}
    # The same list stored inside the new cache file's "keylist" field.
    new = tmp_path / "license.cache.json"
    new.write_text(json.dumps({"v": 1, "keylist": old.read_text()}))
    assert L.load_trusted_keys(root_pem, str(new)) == {"k1": "PEM"}
