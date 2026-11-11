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


def check_online_reply(text: str, keys, license_id: str, now=None, last_seen=None) -> OnlineResult:
    """Verify a signed reply from POST /v1/check (SPEC.md section 5).

    Cache the reply text yourself. Call this again with the cached text when the
    server is unreachable. Once `valid_until` passes, the reply is no longer trusted.
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
    online = check_online_reply(reply_text, keys, license_id, now=now)
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


def load_trusted_keys(root_pem: str, cache_path=None, endpoint=None, timeout=5) -> dict:
    """Return trusted {kid: PEM}. Tries the server first (GET {endpoint}/v1/keys), caches the
    signed list, and falls back to the cache when the network is down. Every list is verified
    with the root key before use. A fetched list older than the cached one is ignored, so an
    old list can't roll back a revocation. Raises ValueError if no valid list is available."""
    import os
    import urllib.request

    cached_text = None
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            cached_text = f.read()

    if endpoint:
        try:
            with urllib.request.urlopen(endpoint.rstrip("/") + "/v1/keys", timeout=timeout) as resp:
                fetched = resp.read().decode("utf-8")
            verify_key_list(fetched, root_pem)  # reject anything not signed by the root
            if cached_text is None or _list_issued_at(fetched) >= _list_issued_at(cached_text):
                if cache_path:
                    with open(cache_path, "w", encoding="utf-8") as f:
                        f.write(fetched)
                return verify_key_list(fetched, root_pem)
        except (OSError, ValueError):
            pass  # network down or bad reply: use the cache below

    if cached_text is not None:
        return verify_key_list(cached_text, root_pem)
    raise ValueError("no trusted key list: the server is unreachable and nothing is cached")
