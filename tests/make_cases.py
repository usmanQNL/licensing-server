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
        else:
            text = json.dumps(signed({**BASE, **changes}))
        case = {"name": name, "mode": mode}
        if needed:
            case["features_needed"] = needed
        case.update({"license": text, "expect": expect})
        out.append(case)

    path = ROOT / "verifiers" / "cases.json"
    path.write_text(json.dumps({"now": NOW, "public_key_pem": pem, "cases": out}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(out)} cases to {path}")


if __name__ == "__main__":
    main()
