"""Licensing Plan: print the installed license plan as JSON.

Run:  python plan.py [license.json] [public.pem] [features.json]
With no arguments it uses the demo files in ../demo/.

It reuses verifiers/python/licensing.py (needs `cryptography`).
"""
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "verifiers", "python"))
from licensing import verify_license  # noqa: E402

DEMO = os.path.join(HERE, "..", "demo")
PLANS = {"opensource", "subscription", "gated", "full"}


def license_plan(text, keys, all_features, now=None):
    """Return the plan as a dict. Fields the license does not carry are None.
    Never raises for a bad license: it returns valid=False with every feature disabled."""
    now = now or datetime.now(timezone.utc)
    try:
        plan = json.loads(text)["payload"]["plan"]
    except (ValueError, KeyError, TypeError):
        plan = None
    if plan not in PLANS:
        result = None
        valid, reason, payload, in_grace = False, "invalid or unreadable license", {}, False
    else:
        result = verify_license(text, keys, mode=plan, now=now)
        valid, reason, payload, in_grace = result.valid_for_paid_features, result.reason, result.payload, result.in_grace
    plan = "subscription" if plan == "full" else plan

    if valid:
        status = "grace" if in_grace else "active"
    elif reason == "license expired":
        status = "expired"
    else:
        status = "invalid"
        payload = {}  # never show fields from a license that failed its signature

    licensed = set(payload.get("features", []))

    def enabled(name):
        return valid and (plan == "subscription" or name in licensed)

    names = list(all_features) + sorted(licensed - set(all_features))
    return {
        "valid": valid,
        "status": status,
        "reason": reason,
        "license_id": payload.get("license_id"),
        "customer": payload.get("customer"),
        "name": plan if payload else None,
        "start": payload.get("issued_at"),
        "expires": payload.get("expires_at"),
        "perpetual": bool(payload) and "expires_at" not in payload,
        "max_installs": payload.get("max_installs", 1) if payload else None,
        "features": [{"name": n, "enabled": enabled(n)} for n in names],
    }


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    args = sys.argv[1:] + [None] * 3
    license_path = args[0] or os.path.join(DEMO, "license-gated.json")
    key_path = args[1] or os.path.join(DEMO, "demo-public.pem")
    features_path = args[2] or os.path.join(DEMO, "features.json")
    plan = license_plan(_read(license_path), _read(key_path), json.loads(_read(features_path)))
    print(json.dumps(plan, indent=2))
