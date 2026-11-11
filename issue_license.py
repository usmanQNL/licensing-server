#!/usr/bin/env python3
"""Issue a signed license file (SPEC.md section 1).

Keep the private key out of git. Use --key-file for a local PEM, or
--key-secret to read it from Google Secret Manager at run time.

Examples:
  python issue_license.py --customer "Example Ltd" --plan subscription --expires-days 365 \
      --features sso,hourly_sync --key-secret license-signing-key --project my-project
  python issue_license.py --customer "Example Ltd" --plan opensource --key-file private.pem
"""
import argparse
import base64
import json
import os
import re
import secrets
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PLANS = ("opensource", "subscription", "gated", "full")  # "full" is a legacy alias for "subscription"


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def load_key(args) -> Ed25519PrivateKey:
    if args.key_file:
        with open(args.key_file, "rb") as f:
            pem = f.read()
    else:
        cmd = ["gcloud", "secrets", "versions", "access", "latest", "--secret", args.key_secret]
        if args.project:
            cmd += ["--project", args.project]
        pem = subprocess.run(cmd, check=True, capture_output=True).stdout
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        sys.exit("error: the signing key must be Ed25519")
    return key


def make_license_id() -> str:
    return "LIC-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + secrets.token_hex(3).upper()


def parse_args():
    p = argparse.ArgumentParser(
        description="Issue a signed license file for a customer.",
        epilog="Exactly one of --key-file or --key-secret is required.",
    )
    p.add_argument("--customer", required=True, help="Customer name, shown in the license.")
    p.add_argument("--application", required=True, help="Application the license is for, e.g. QuellDAP.")
    p.add_argument("--client-email", required=True,
                   help="Contact email for the customer. Stored in the license store only, never in the license file.")
    p.add_argument("--client-phone", default="",
                   help="Optional contact phone. Stored in the license store only, never in the license file.")
    p.add_argument("--firestore-project",
                   help="Also register the license in this Firestore project (licenses collection).")
    p.add_argument("--json-path",
                   help="Also register the license in this JSON file (local use). Pick one backend.")
    p.add_argument("--plan", required=True, choices=PLANS, help="Licensing mode for this product.")
    p.add_argument("--features", default="", help="Comma-separated feature names (gated mode).")
    p.add_argument("--license-id", help="Optional ID. Default: LIC-<date>-<random>.")
    p.add_argument("--expires-days", type=int, help="Expire this many days after issue. Omit for perpetual.")
    p.add_argument("--kid", default="k1",
                   help="Key ID of the signing key (key rotation). Must match a key the app trusts. Default k1.")
    p.add_argument("--max-installs", type=int, default=1,
                   help="How many installs this license covers (seat limit, enforced by the online check). Default 1.")
    p.add_argument("--expires-on", help="Expiry date, YYYY-MM-DD (UTC). Overrides --expires-days.")
    p.add_argument("--keylist", default="keylist.json",
                   help="Last signed key list (from sign_keylist.py). Warns if --kid is not in it. Default keylist.json.")
    key = p.add_mutually_exclusive_group(required=True)
    key.add_argument("--key-file", help="Path to the Ed25519 private key PEM. Keep it out of git.")
    key.add_argument("--key-secret", help="Google Secret Manager secret name holding the PEM.")
    p.add_argument("--project", help="Google Cloud project, used with --key-secret.")
    p.add_argument("--out", help="Output path. Default: licenses/<application>/<license_id>.license.json")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the payload and the output path, and write nothing (no file, no store).")
    args = p.parse_args()
    if args.plan == "full":
        print("warning: plan 'full' is now 'subscription'. Writing 'subscription'.", file=sys.stderr)
        args.plan = "subscription"
    return args


def check_keylist(args) -> None:
    """Warn if the kid is not in the last signed key list, so apps can trust the license.
    Reads only the public list. The root key is never needed here."""
    if not os.path.exists(args.keylist):
        print(f"warning: no key list at {args.keylist}. Make sure apps trust kid {args.kid!r} "
              "before you send this license.", file=sys.stderr)
        return
    with open(args.keylist, encoding="utf-8") as f:
        payload = json.load(f).get("payload", {})
    if args.kid in payload.get("revoked", []):
        print(f"warning: kid {args.kid!r} is revoked in {args.keylist}. Licenses signed with it will not verify.",
              file=sys.stderr)
    elif args.kid not in payload.get("keys", {}):
        print(f"warning: kid {args.kid!r} is not in {args.keylist}. Sign and upload a new key list "
              "(sign_keylist.py) before sending this license.", file=sys.stderr)


def main():
    args = parse_args()
    check_keylist(args)
    if args.key_secret and not args.project:
        print("note: --project not set, gcloud default project will be used", file=sys.stderr)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    payload = {
        "v": 1,
        "license_id": args.license_id or make_license_id(),
        "customer": args.customer,
        "plan": args.plan,
        "features": [f.strip() for f in args.features.split(",") if f.strip()],
        "max_installs": args.max_installs,
        "issued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if args.max_installs < 1:
        sys.exit("error: --max-installs must be at least 1")

    if args.expires_on:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.expires_on):
            sys.exit("error: --expires-on must be YYYY-MM-DD")
        expires = datetime.strptime(args.expires_on, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        payload["expires_at"] = expires.strftime("%Y-%m-%dT%H:%M:%SZ")
    elif args.expires_days:
        payload["expires_at"] = (now + timedelta(days=args.expires_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    if args.plan == "gated" and not payload["features"]:
        print("warning: gated license has no features, so nothing can be unlocked", file=sys.stderr)

    signature = load_key(args).sign(canonical_bytes(payload))
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        print(f"contact (license store only): {args.client_email}" + (f", {args.client_phone}" if args.client_phone else ""))
        print("dry run: nothing written")
        return

    if args.out:
        out = args.out
    else:
        app_dir = re.sub(r"[^A-Za-z0-9._-]+", "-", args.application).strip("-") or "app"
        os.makedirs(os.path.join("licenses", app_dir), exist_ok=True)
        out = os.path.join("licenses", app_dir, f"{payload['license_id']}.license.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"kid": args.kid, "payload": payload, "signature": b64url(signature)}, f, indent=2)
        f.write("\n")
    print(f"wrote {out}")

    if args.firestore_project or args.json_path or os.environ.get("LICENSE_STORAGE"):
        register_license(args, payload)


def register_license(args, payload: dict) -> None:
    """Create or update the license record (SPEC.md section 6). Works with any storage backend."""
    from app.storage import build_admin_storage

    store = build_admin_storage(args.firestore_project, args.json_path)
    doc = {
        "status": "active",
        "customer": payload["customer"],
        "application": args.application,
        "client_email": args.client_email,
        "client_phone": args.client_phone,
        "plan": payload["plan"],
        "features": payload["features"],
        "max_installs": payload["max_installs"],
        "issued_at": payload["issued_at"],
        "expires_at": payload.get("expires_at"),
    }
    store.put_license(payload["license_id"], doc)
    target = args.firestore_project and f"Firestore project {args.firestore_project}" or args.json_path or "the server's storage"
    print(f"registered {payload['license_id']} in {target}")


if __name__ == "__main__":
    main()
