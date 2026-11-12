"""Regenerate verifiers/cases.json, the shared license fixtures every verifier must pass.

Run from the repo root:  python tests/make_cases.py
It signs every case with a new throwaway Ed25519 key and does not save the private key.
Add a case to CASES below, run this, then run every verifier's tests.
"""
import base64
import json
import pathlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOW = "2026-11-10T12:00:00Z"
BASE = {"v": 1, "license_id": "LIC-1", "customer": "Example", "issued_at": "2026-10-11T12:00:00Z"}
ISSUER = "https://licensing.example.com"
OTHER_ISSUER = "https://evil.example.net"

# Online replies checked against a license's issuer_url (SPEC.md section 5), at NOW.
# (name, license issuer_url, reply issuer_url, reply status, expect active)
ISSUER_CASES = [
    ("same_issuer", ISSUER, ISSUER, "active", True),
    ("same_issuer_trailing_slash", ISSUER, ISSUER + "/", "active", True),
    ("different_issuer", ISSUER, OTHER_ISSUER, "active", False),
    ("old_license_new_reply", None, ISSUER, "active", True),
    ("new_license_old_reply", ISSUER, None, "active", True),
    ("same_issuer_revoked", ISSUER, ISSUER, "revoked", False),
]

# (name, mode, payload changes, features_needed, expect). Times are relative to NOW:
# 2026-12-10 is in the future, 2026-11-05 is in the 14-day grace period, 2026-10-21 is past grace.
CASES = [
    ("full_valid", "full", {"plan": "full", "expires_at": "2026-12-10T12:00:00Z"}, None, True),
    ("full_grace", "full", {"plan": "full", "expires_at": "2026-11-05T12:00:00Z"}, None, True),
    ("full_expired", "full", {"plan": "full", "expires_at": "2026-10-21T12:00:00Z"}, None, False),
    ("plan_mismatch", "full", {"plan": "gated", "expires_at": "2026-12-10T12:00:00Z"}, None, False),
    ("tampered", "full", None, None, False),
    ("gated_has_feature", "gated", {"plan": "gated", "features": ["sso"]}, ["sso"], True),
    ("gated_missing_feature", "gated", {"plan": "gated", "features": ["hourly_sync"]}, ["sso"], False),
    ("gated_with_end_date_valid", "gated", {"plan": "gated", "features": ["sso"], "expires_at": "2026-12-10T12:00:00Z"}, ["sso"], True),
    ("gated_with_end_date_grace", "gated", {"plan": "gated", "features": ["sso"], "expires_at": "2026-11-05T12:00:00Z"}, ["sso"], True),
    ("gated_with_end_date_expired", "gated", {"plan": "gated", "features": ["sso"], "expires_at": "2026-10-21T12:00:00Z"}, ["sso"], False),
    ("unsupported_version", "opensource", {"v": 2, "plan": "opensource"}, None, False),
    # issuer_url is optional. Licenses with it verify the same way; editing it breaks the signature.
    ("subscription_with_issuer_url", "subscription", {"plan": "subscription", "expires_at": "2026-12-10T12:00:00Z", "issuer_url": ISSUER}, None, True),
    ("issuer_url_tampered", "subscription", None, None, False),
    ("garbage", "full", None, None, False),
]


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def main():
    key = Ed25519PrivateKey.generate()
    pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()

    def signed(payload):
        sig = base64.urlsafe_b64encode(key.sign(canonical(payload))).rstrip(b"=").decode()
        return {"payload": payload, "signature": sig}

    out = []
    for name, mode, changes, needed, expect in CASES:
        if name == "garbage":
            text = "not json"
        elif name == "tampered":
            # The signature of a valid subscription license, over a payload changed to opensource.
            doc = signed({**BASE, "plan": "full", "expires_at": "2026-12-10T12:00:00Z"})
            doc["payload"]["plan"] = "opensource"
            text = json.dumps(doc)
        elif name == "issuer_url_tampered":
            # A valid license whose issuer_url was edited to point at another server.
            doc = signed({**BASE, "plan": "subscription", "expires_at": "2026-12-10T12:00:00Z", "issuer_url": ISSUER})
            doc["payload"]["issuer_url"] = OTHER_ISSUER
            text = json.dumps(doc)
        else:
            text = json.dumps(signed({**BASE, **changes}))
        case = {"name": name, "mode": mode}
        if needed:
            case["features_needed"] = needed
        case.update({"license": text, "expect": expect})
        out.append(case)

    issuer_cases = []
    for name, lic_issuer, reply_issuer, status, expect in ISSUER_CASES:
        reply = {"v": 1, "license_id": "LIC-1", "status": status, "max_installs": 1,
                 "checked_at": "2026-11-10T11:00:00Z", "valid_until": "2026-11-17T11:00:00Z"}
        if reply_issuer:
            reply["issuer_url"] = reply_issuer
        issuer_cases.append({"name": name, "license_id": "LIC-1", "license_issuer_url": lic_issuer,
                             "reply": json.dumps(signed(reply)), "expect_active": expect})

    path = ROOT / "verifiers" / "cases.json"
    path.write_text(json.dumps({"now": NOW, "public_key_pem": pem, "cases": out, "issuer_cases": issuer_cases},
                               indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(out)} license cases and {len(issuer_cases)} issuer cases to {path}")


if __name__ == "__main__":
    main()
