"""License verifier (SPEC.md sections 1 to 5). Requires: cryptography.

Usage:
    from licensing import verify_license, LicenseResult
    result = verify_license(license_json_text, PUBLIC_KEY_PEM, mode="subscription", now=None)
    if result.valid_for_paid_features:
        ...
"""
import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SUPPORTED_VERSION = 1
GRACE_PERIOD = timedelta(days=14)
MODES = ("opensource", "subscription", "gated")
# "full" was merged into "subscription". Licenses issued as "full" still verify.
LEGACY_PLAN_ALIASES = {"full": "subscription"}


def _canonical_plan(name):
    return LEGACY_PLAN_ALIASES.get(name, name)


@dataclass
class LicenseResult:
    valid_for_paid_features: bool
    reason: str
    payload: dict = field(default_factory=dict)
    in_grace: bool = False


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _parse_time(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def load_public_key(pem: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem.encode())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("public key must be Ed25519")
    return key


def pick_key(keys, kid):
    """keys is one PEM string, or a dict of {kid: PEM} to support key rotation (SPEC.md section 2)."""
    if isinstance(keys, str):
        return keys
    if kid is None or kid not in keys:
        raise ValueError("no trusted key for kid " + repr(kid))
    return keys[kid]


def verify_license(text: str, keys, mode: str, features_needed=(), now=None) -> LicenseResult:
    """Verify a license file. Never raises for bad input: it returns valid_for_paid_features=False.
    keys: a PEM string, or {kid: PEM} when the app trusts more than one key."""
    mode = _canonical_plan(mode)
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    now = now or datetime.now(timezone.utc)

    try:
        doc = json.loads(text)
        payload = doc["payload"]
        signature = _b64url_decode(doc["signature"])
        load_public_key(pick_key(keys, doc.get("kid"))).verify(signature, _canonical(payload))
    except (ValueError, KeyError, TypeError, InvalidSignature):
        return LicenseResult(False, "invalid or unreadable license")

    if payload.get("v") != SUPPORTED_VERSION:
        return LicenseResult(False, "unsupported license version", payload)

    plan = _canonical_plan(payload.get("plan"))
    if mode != "opensource" and plan != mode:
        return LicenseResult(False, f"license is for plan '{plan}', app is '{mode}'", payload)

    in_grace = False
    if mode in ("subscription", "gated") and "expires_at" in payload:
        expires = _parse_time(payload["expires_at"])
        if now > expires:
            if now <= expires + GRACE_PERIOD:
                in_grace = True
            else:
                return LicenseResult(False, "license expired", payload)

    if mode == "gated":
        features = set(payload.get("features", []))
        missing = [f for f in features_needed if f not in features]
        if missing:
            return LicenseResult(False, f"feature not licensed: {', '.join(missing)}", payload)

    return LicenseResult(True, "in grace period" if in_grace else "valid", payload, in_grace)


@dataclass
class OnlineResult:
    active: bool  # true means paid features may stay on
    status: str  # "active" | "revoked" | "unknown" | "limit_reached" | "invalid"
    reason: str
    valid_until: str = ""
    fresh: bool = False  # true if the reply is verified and still within valid_until


CLOCK_TOLERANCE = timedelta(minutes=5)


def clock_moved_back(now, last_seen) -> bool:
    """True if the clock is earlier than the newest time this app has seen (SPEC.md section 8).
    Store max(now) after each check and pass it back as last_seen. This stops cached replies
    and licenses from being extended by setting the clock back."""
    return last_seen is not None and now < last_seen - CLOCK_TOLERANCE


def valid_issuer_url(url) -> bool:
    """issuer_url must be https. http is accepted only for localhost, for local tests."""
    from urllib.parse import urlparse
    if not isinstance(url, str) or len(url) > 2048:
        return False
    parts = urlparse(url)
    if parts.scheme == "https":
        return bool(parts.hostname)
    return parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")


def _norm_url(url):
    return url.rstrip("/") if isinstance(url, str) else url


def same_issuer(license_issuer, reply_issuer) -> bool:
    """True unless both sides name an issuer and they differ. Licenses and replies from before
    issuer_url existed have none, and still match (SPEC.md section 5)."""
    if not license_issuer or not reply_issuer:
        return True
    return _norm_url(license_issuer) == _norm_url(reply_issuer)


def check_online_reply(text: str, keys, license_id: str, now=None, last_seen=None, issuer_url=None) -> OnlineResult:
    """Verify a signed reply from POST /v1/check (SPEC.md section 5).

    refresh_online_status() fetches and caches replies for you. Call this again with the cached
    text when the server is unreachable. Once `valid_until` passes, the reply is no longer trusted.
    issuer_url: the license's issuer_url. When both it and the reply have one, they must match.
    Never throws for bad input.
    """
    now = now or datetime.now(timezone.utc)
    if clock_moved_back(now, last_seen):
        return OnlineResult(False, "invalid", "system clock moved backwards")
    try:
        doc = json.loads(text)
        payload = doc["payload"]
        signature = _b64url_decode(doc["signature"])
        load_public_key(pick_key(keys, doc.get("kid"))).verify(signature, _canonical(payload))
    except (ValueError, KeyError, TypeError, InvalidSignature):
        return OnlineResult(False, "invalid", "invalid or unreadable reply")

    if payload.get("v") != SUPPORTED_VERSION:
        return OnlineResult(False, "invalid", "unsupported reply version")
    if payload.get("license_id") != license_id:
        return OnlineResult(False, "invalid", "reply is for a different license")
    if not same_issuer(issuer_url, payload.get("issuer_url")):
        return OnlineResult(False, "invalid", "reply is from a different issuer")

    status = payload.get("status", "unknown")
    valid_until = payload.get("valid_until", "")
    try:
        if now > _parse_time(valid_until):
            return OnlineResult(False, status, "cached reply is too old, check again", valid_until, fresh=False)
    except ValueError:
        return OnlineResult(False, "invalid", "invalid valid_until", valid_until)

    if status == "active":
        return OnlineResult(True, status, "active", valid_until, fresh=True)
    if status == "limit_reached":
        return OnlineResult(False, status, "seat limit reached for this license", valid_until, fresh=True)
    if status == "revoked":
        return OnlineResult(False, status, "license revoked", valid_until, fresh=True)
    return OnlineResult(False, "unknown", "license not recognised by the server", valid_until, fresh=True)


def evaluate(text: str, keys, mode: str, license_id: str, reply_text=None, features_needed=(), now=None, last_seen=None) -> LicenseResult:
    """One decision for the app: should paid features be on right now?

    - The local license must be valid (signature, plan, expiry, grace, features).
    - If a fresh online reply says the license is revoked, unknown, or over its seat limit, paid features are off.
    - If there is no reply, or the cached reply is too old, the local license decides (offline use).
    Sign-in is never blocked by this function.
    """
    now = now or datetime.now(timezone.utc)
    if clock_moved_back(now, last_seen):
        return LicenseResult(False, "system clock moved backwards")
    local = verify_license(text, keys, mode, features_needed, now=now)
    if not local.valid_for_paid_features or reply_text is None:
        return local
    online = check_online_reply(reply_text, keys, license_id, now=now, issuer_url=local.payload.get("issuer_url"))
    if online.fresh and not online.active:
        return LicenseResult(False, online.reason, local.payload, local.in_grace)
    return local


# ---- Signed key list (SPEC.md section 2a) ----------------------------------

def verify_key_list(text: str, root_pem: str) -> dict:
    """Verify a signed key list with the baked-in root key. Returns {kid: PEM} of trusted signing keys.
    Raises ValueError if the list is malformed, has the wrong signer, or fails the signature."""
    try:
        env = json.loads(text)
        payload = env["payload"]
        signature = _b64url_decode(env["signature"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("malformed key list") from exc
    if env.get("kid") != "root":
        raise ValueError("key list is not signed by the root key")
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise ValueError("unsupported key list version")
    try:
        load_public_key(root_pem).verify(signature, _canonical(payload))
    except InvalidSignature as exc:
        raise ValueError("bad key list signature") from exc
    revoked = set(payload.get("revoked", []))
    return {kid: pem for kid, pem in payload.get("keys", {}).items() if kid not in revoked}


def _list_issued_at(text: str) -> str:
    return json.loads(text)["payload"].get("issued_at", "")


# ---- License cache file (.env: <APP_NAME>_LICENSE_CACHE) -------------------
# One JSON file per install holds everything fetched from the licensing server:
#   {"v": 1, "license_id", "issuer_url", "install_hash", "install_token",
#    "reply": <signed /v1/check reply, as text>, "checked_at", "last_seen",
#    "keylist": <signed key list, as text>}
# Nothing in it is secret except install_token, and nothing in it is trusted without its signature.
# It is signed data, not encrypted data. A missing or damaged cache is treated as empty.

CACHE_VERSION = 1


def _read_cache(path) -> dict:
    """The cache as a dict. An older key-list-only cache file (a bare signed key list) is read as
    {"keylist": text}. Missing or unreadable: {}."""
    import os
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        doc = json.loads(text)
    except (OSError, ValueError):
        return {}
    if not isinstance(doc, dict):
        return {}
    if "payload" in doc and "signature" in doc:
        return {"keylist": text, "_legacy_keylist": True}
    return doc


def _write_cache(path, state: dict) -> None:
    """Write the cache atomically (temp file, then rename), creating the folder if needed."""
    import os
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in state.items() if not k.startswith("_")}, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_trusted_keys(root_pem: str, cache_path=None, endpoint=None, timeout=5) -> dict:
    """Return trusted {kid: PEM}. Tries the server first (GET {endpoint}/v1/keys), caches the
    signed list in the license cache file (its "keylist" field), and falls back to the cache when
    the network is down. Every list is verified with the root key before use. A fetched list older
    than the cached one is ignored, so an old list can't roll back a revocation.
    An older cache file that holds only a bare key list is still read and kept in that format.
    Raises ValueError if no valid list is available."""
    import urllib.request

    state = _read_cache(cache_path)
    cached_text = state.get("keylist")

    if endpoint:
        try:
            with urllib.request.urlopen(endpoint.rstrip("/") + "/v1/keys", timeout=timeout) as resp:
                fetched = resp.read().decode("utf-8")
            verify_key_list(fetched, root_pem)  # reject anything not signed by the root
            if cached_text is None or _list_issued_at(fetched) >= _list_issued_at(cached_text):
                if cache_path:
                    if state.get("_legacy_keylist"):
                        with open(cache_path, "w", encoding="utf-8") as f:
                            f.write(fetched)
                    else:
                        _write_cache(cache_path, {**state, "v": CACHE_VERSION, "keylist": fetched})
                return verify_key_list(fetched, root_pem)
        except (OSError, ValueError):
            pass  # network down or bad reply: use the cache below

    if cached_text is not None:
        return verify_key_list(cached_text, root_pem)
    raise ValueError("no trusted key list: the server is unreachable and nothing is cached")


def _verified_payload(text: str, keys):
    """The license payload if its signature checks out, else None. Plan and expiry are not checked here."""
    try:
        doc = json.loads(text)
        payload = doc["payload"]
        load_public_key(pick_key(keys, doc.get("kid"))).verify(_b64url_decode(doc["signature"]), _canonical(payload))
        return payload if isinstance(payload, dict) else None
    except (ValueError, KeyError, TypeError, InvalidSignature):
        return None


def _fmt_time(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _time_or_none(text):
    try:
        return _parse_time(text) if text else None
    except (ValueError, TypeError):
        return None


@dataclass
class OnlineStatus:
    reply_text: str = None  # last valid signed reply (fresh or cached); pass to evaluate()
    last_seen: datetime = None  # newest time seen; pass to evaluate()
    issuer_url: str = ""  # the server this install checks with
    contacted: bool = False  # true if the server answered this time
    reason: str = ""


def refresh_online_status(license_text: str, keys, cache_path, endpoint=None, now=None, timeout=5,
                          min_interval=timedelta(hours=24)) -> OnlineStatus:
    """Run the daily online check (SPEC.md section 5) and keep the license cache up to date.

    - The server is the license's signed issuer_url. Licenses without one use `endpoint`
      (the app's configured server URL). With neither, nothing is sent.
    - Sends {license_id, install_hash, install_token} to POST {server}/v1/check, at most once per
      min_interval. install_hash is created once and kept in the cache, and so is the install_token
      the server returns on activation.
    - Keeps the last valid signed reply and last_seen in the cache. When the server can't be reached,
      the cached reply is returned, and it stays trusted only until its valid_until.
    - A cache made for another license or another server is started fresh (the key list is kept).
    Never raises for network errors. Then call:
        evaluate(license_text, keys, mode, license_id, reply_text=s.reply_text, last_seen=s.last_seen)
    """
    import secrets
    import urllib.error
    import urllib.request

    now = now or datetime.now(timezone.utc)
    payload = _verified_payload(license_text, keys)
    if payload is None:
        return OnlineStatus(reason="license is invalid, nothing sent")
    license_id = payload.get("license_id")
    issuer = payload.get("issuer_url")
    server = issuer if valid_issuer_url(issuer) else endpoint
    server = _norm_url(server) or ""

    state = _read_cache(cache_path)
    if state.get("license_id") != license_id or (state.get("issuer_url") or "") != server:
        state = {"keylist": state["keylist"]} if "keylist" in state else {}
    state.update({"v": CACHE_VERSION, "license_id": license_id, "issuer_url": server})
    state.pop("_legacy_keylist", None)
    state.setdefault("install_hash", secrets.token_urlsafe(18))

    last_seen = _time_or_none(state.get("last_seen"))
    newest = max(now, last_seen) if last_seen else now
    checked_at = _time_or_none(state.get("checked_at"))
    contacted, reason = False, "using cached reply"

    if not server:
        reason = "no server configured, offline only"
    elif checked_at and checked_at <= now < checked_at + min_interval:
        reason = "checked recently, using cached reply"
    else:
        body = {"license_id": license_id, "install_hash": state["install_hash"]}
        if state.get("install_token"):
            body["install_token"] = state["install_token"]
        req = urllib.request.Request(server + "/v1/check", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8")
            result = check_online_reply(text, keys, license_id, now=now, issuer_url=issuer)
            if result.status == "invalid":
                reason = "server reply rejected: " + result.reason
            else:
                contacted, reason = True, result.reason
                state["reply"] = text
                state["checked_at"] = _fmt_time(now)
                token = json.loads(text)["payload"].get("install_token")
                if token:
                    state["install_token"] = token
        except urllib.error.HTTPError as exc:
            reason = f"server answered HTTP {exc.code}, using cached reply"
        except (OSError, ValueError):
            reason = "server unreachable, using cached reply"

    state["last_seen"] = _fmt_time(newest)
    if cache_path:
        try:
            _write_cache(cache_path, state)
        except OSError:
            reason += " (cache not writable)"
    return OnlineStatus(state.get("reply"), newest, server, contacted, reason)


# ---- Locating the license file (.env: <APP_NAME>_LICENSE_FILE) -------------

def _env_stem(app_name: str) -> str:
    import re
    stem = re.sub(r"[^A-Z0-9]+", "_", app_name.upper()).strip("_") or "APP"
    if stem[0].isdigit():
        stem = "APP_" + stem
    return stem


def license_file_env_var(app_name: str) -> str:
    """Name of the .env variable that holds the license file's location, for example
    "QuellDAP" -> "QUELLDAP_LICENSE_FILE". Uppercase; every run of other characters becomes "_"."""
    return _env_stem(app_name) + "_LICENSE_FILE"


def license_cache_env_var(app_name: str) -> str:
    """Name of the .env variable that holds the license cache file's location,
    for example "QuellDAP" -> "QUELLDAP_LICENSE_CACHE"."""
    return _env_stem(app_name) + "_LICENSE_CACHE"


# Used when <APP>_LICENSE_FILE is not set: license.json in the current working directory.
DEFAULT_LICENSE_FILE = "license.json"


def read_dotenv(path: str) -> dict:
    """Read KEY=VALUE lines from a .env file. Missing file: {}. Comments and blank lines are skipped."""
    values = {}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def find_license_file(app_name: str, project_root: str = ".") -> str:
    """Absolute path of the license file. <APP>_LICENSE_FILE holds the full path; it is read from the
    environment first, then from <project_root>/.env. A relative value is resolved against project_root.
    When the variable is unset: license.json in the current working directory.
    The file may not exist: treat that as no license."""
    import os
    value = _setting(license_file_env_var(app_name), project_root)
    if value:
        return os.path.abspath(os.path.join(project_root, value))
    return os.path.abspath(os.path.join(os.getcwd(), DEFAULT_LICENSE_FILE))


def _setting(var: str, project_root: str):
    """A variable from the environment, then from <project_root>/.env. Empty counts as unset."""
    import os
    return os.environ.get(var) or read_dotenv(os.path.join(project_root, ".env")).get(var) or None


def default_cache_file(license_file: str) -> str:
    """The cache file used when <APP>_LICENSE_CACHE is unset: next to the license file, named after it.
    license.json -> license.cache.json, LIC-1.license.json -> LIC-1.license.cache.json."""
    import os
    folder, name = os.path.split(os.path.abspath(license_file))
    stem = name[:-5] if name.lower().endswith(".json") else name
    return os.path.join(folder, stem + ".cache.json")


def find_license_cache(app_name: str, project_root: str = ".") -> str:
    """Absolute path of the license cache file. <APP>_LICENSE_CACHE holds the full path, read from the
    environment first, then from <project_root>/.env. A relative value is resolved against project_root.
    When unset: <license file name>.cache.json next to the license file (see find_license_file).
    The file may not exist yet: refresh_online_status and load_trusted_keys create it."""
    import os
    value = _setting(license_cache_env_var(app_name), project_root)
    if value:
        return os.path.abspath(os.path.join(project_root, value))
    return default_cache_file(find_license_file(app_name, project_root))
