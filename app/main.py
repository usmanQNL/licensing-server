"""Online license check server (SPEC.md sections 5 and 6)."""
import hashlib
import logging
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .signing import load_private_key, sign_payload
from .storage import build_storage

VALID_FOR = timedelta(days=int(os.environ.get("LICENSE_VALID_DAYS", "7")))
# This server's public URL, signed into every reply as issuer_url (SPEC.md section 5).
# Set it to the same value issue_license.py writes into licenses (--issuer-url). Unset: no issuer_url.
ISSUER_URL = os.environ.get("LICENSE_ISSUER_URL", "").strip().rstrip("/")
log = logging.getLogger("license-check")

app = FastAPI(title="License check", version="1")
storage = build_storage()

# Abuse protection. Limits are per instance and per client IP. For a hard global limit,
# add Cloud Armor (or your gateway's) rate limiting in front of the service as well.
RATE_LIMIT_PER_MIN = int(os.environ.get("LICENSE_RATE_LIMIT_PER_MIN", "60"))
MAX_BODY_BYTES = 2048
SWEEP_AT = 5000  # drop idle client entries when the table grows past this size
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    # Cloud Run appends the real client address to X-Forwarded-For, so the last entry is the
    # one the client can't forge. The first entry is whatever the client sent.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _sweep(now: float) -> None:
    for ip in list(_hits):
        hits = _hits[ip]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if not hits:
            del _hits[ip]


@app.middleware("http")
async def limit_abuse(request: Request, call_next):
    if request.method == "POST":
        length = request.headers.get("content-length")
        if length and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "request too large"}, status_code=413)
        ip = _client_ip(request)
        now = time.monotonic()
        with _hits_lock:
            if len(_hits) > SWEEP_AT:
                _sweep(now)
            hits = _hits[ip]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= RATE_LIMIT_PER_MIN:
                log.warning("rate limited ip=%s", ip)
                return JSONResponse({"detail": "too many requests"}, status_code=429,
                                    headers={"Retry-After": "60"})
            hits.append(now)
    return await call_next(request)


def _signing_key():
    """Reads the key from LICENSE_SIGNING_KEY_PATH (file) or LICENSE_SIGNING_KEY (PEM text).
    Google Secret Manager support can be added here later without touching callers."""
    path = os.environ.get("LICENSE_SIGNING_KEY_PATH")
    if path:
        with open(path, "rb") as f:
            return load_private_key(f.read())
    pem = os.environ.get("LICENSE_SIGNING_KEY")
    if not pem:
        raise RuntimeError("no signing key configured")
    return load_private_key(pem.encode())


signing_key = None


class CheckRequest(BaseModel):
    license_id: str = Field(min_length=1, max_length=128)
    install_hash: str = Field(min_length=8, max_length=128)
    # Sent by the app on every check after the first. The server issued it on activation.
    install_token: str | None = Field(default=None, max_length=128)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@app.get("/v1/health")
def health():
    return {"ok": True}


@app.get("/v1/keys")
def keys():
    """Serves the signed key list (SPEC.md section 2a). The list is signed offline with the
    root key by sign_keylist.py. This server never holds the root key, so it only
    returns the file it was given, byte for byte, as the signed envelope."""
    path = os.environ.get("LICENSE_KEYLIST_PATH")
    if not path or not os.path.exists(path):
        return JSONResponse({"detail": "key list not configured"}, status_code=503)
    with open(path, "rb") as f:
        return Response(content=f.read(), media_type="application/json",
                        headers={"Cache-Control": "public, max-age=3600"})


@app.post("/v1/check")
def check(req: CheckRequest):
    global signing_key
    if signing_key is None:
        signing_key = _signing_key()

    seen = datetime.now(timezone.utc)
    seen_iso = seen.strftime("%Y-%m-%dT%H:%M:%SZ")
    lic = storage.get_license(req.license_id)
    max_installs = int((lic or {}).get("max_installs", 1))
    install = storage.get_install(req.license_id, req.install_hash) if lic else None
    issued_token = None

    if lic is None:
        status = "unknown"
    elif lic.get("status") == "revoked":
        status = "revoked"
    elif install is not None:
        # A known install must prove it holds the token it was given at activation.
        if req.install_token is None or install.get("token_hash") != _token_hash(req.install_token):
            return JSONResponse({"detail": "install token required or invalid"}, status_code=403)
        status = "active"
    elif storage.count_installs(req.license_id) >= max_installs:
        # Seat limit reached: this install does not hold one of the licensed seats.
        status = "limit_reached"
    else:
        # New install with a free seat: activate it and hand back its token once.
        status = "active"
        issued_token = secrets.token_urlsafe(32)

    if status == "active":
        token_hash = _token_hash(issued_token) if issued_token else None
        storage.save_install(req.license_id, req.install_hash, seen_iso, token_hash=token_hash)

    payload = {
        "v": 1,
        "license_id": req.license_id,
        "status": status,
        "max_installs": max_installs,
        "checked_at": seen_iso,
        "valid_until": (seen + VALID_FOR).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if ISSUER_URL:
        payload["issuer_url"] = ISSUER_URL
    if issued_token:
        payload["install_token"] = issued_token
    return sign_payload(signing_key, payload, kid=os.environ.get("LICENSE_KID", "k1"))
