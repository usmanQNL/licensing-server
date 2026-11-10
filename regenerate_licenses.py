#!/usr/bin/env python3
"""Reissue every active license under a new signing key (key rotation or compromise).

Reads the active licenses from the storage backend and writes new signed license files. The
backend is read only: nothing is written back. Each license keeps its license_id, customer, plan, features,
max_installs, issued_at and expires_at, so a customer's entitlement does not change. Only the
signature and kid change.

Retention: licenses that expired more than 30 days ago are skipped (SPEC retention policy).

Before you run this with the new key:
  1. Add the new public key to keys.json and sign a new key list (sign_keylist.py sign).
  2. Upload keylist.json to the server, so installed apps trust the new kid.
Then reissue. Send each customer their new file, using client_email or client_phone.

Examples:
  python regenerate_licenses.py --firestore-project my-project --application QuellDAP \
      --new-kid k2 --key-secret license-signing-key-k2 --project my-project --dry-run
  python regenerate_licenses.py --firestore-project my-project --application QuellDAP \
      --new-kid k2 --key-file private-k2.pem
"""
import argparse
import base64
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.storage import build_admin_storage  # noqa: E402

RETENTION_AFTER_EXPIRY = timedelta(days=30)
PAYLOAD_FIELDS = ("license_id", "customer", "plan", "features", "max_installs", "issued_at", "expires_at")


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


def parse_time(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def load_active_licenses(args) -> list:
    store = build_admin_storage(args.firestore_project, args.json_path)
    return store.list_licenses(status="active", application=args.application)


def build_payload(doc: dict) -> dict:
    payload = {k: doc[k] for k in PAYLOAD_FIELDS if doc.get(k) is not None}
    payload.setdefault("features", [])
    payload.setdefault("max_installs", 1)
    payload["v"] = 1
    return {k: payload[k] for k in sorted(payload)}


def main():
    p = argparse.ArgumentParser(description="Reissue active licenses under a new signing kid.")
    backend = p.add_mutually_exclusive_group()
    backend.add_argument("--firestore-project", help="Google Cloud project holding the licenses (Firestore backend).")
    backend.add_argument("--json-path", help="License JSON file (JSON backend).")
    p.add_argument("--application", help="Only reissue licenses for this application.")
    p.add_argument("--new-kid", required=True, help="Kid of the new signing key, e.g. k2.")
    key = p.add_mutually_exclusive_group(required=True)
    key.add_argument("--key-file", help="Path to the new Ed25519 private key PEM.")
    key.add_argument("--key-secret", help="Secret Manager secret holding the new PEM.")
    p.add_argument("--project", help="Google Cloud project for --key-secret.")
    p.add_argument("--out-dir", help="Output folder. Default: licenses/<application>/<new-kid>/")
    p.add_argument("--dry-run", action="store_true", help="Count and list what would be written. Write nothing.")
    args = p.parse_args()

    now = datetime.now(timezone.utc)
    docs = load_active_licenses(args)
    if not docs:
        sys.exit("no active licenses found")

    to_issue, skipped = [], []
    for doc in docs:
        expires = parse_time(doc.get("expires_at"))
        if expires and now - expires > RETENTION_AFTER_EXPIRY:
            skipped.append(doc["license_id"])
        else:
            to_issue.append(doc)

    print(f"active licenses: {len(docs)}, to reissue: {len(to_issue)}, "
          f"skipped (expired over 30 days): {len(skipped)}")
    for doc in to_issue:
        print(f"  {doc['license_id']}  {doc.get('plan')}  {doc.get('customer')}")

    if args.dry_run:
        print("dry run: nothing written")
        return

    app_dir = re.sub(r"[^A-Za-z0-9._-]+", "-", args.application or "app").strip("-") or "app"
    out_dir = args.out_dir or os.path.join("licenses", app_dir, args.new_kid)
    os.makedirs(out_dir, exist_ok=True)
    key_obj = load_key(args)

    contacts = []
    for doc in to_issue:
        payload = build_payload(doc)
        signature = key_obj.sign(canonical_bytes(payload))
        path = os.path.join(out_dir, f"{payload['license_id']}.license.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"kid": args.new_kid, "payload": payload, "signature": b64url(signature)}, f, indent=2)
            f.write("\n")
        contacts.append({
            "license_id": payload["license_id"],
            "customer": doc.get("customer", ""),
            "client_email": doc.get("client_email", ""),
            "client_phone": doc.get("client_phone", ""),
        })

    contacts_path = os.path.join(out_dir, "contacts.csv")
    with open(contacts_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["license_id", "customer", "client_email", "client_phone"])
        writer.writeheader()
        writer.writerows(contacts)

    print(f"wrote {len(to_issue)} license files to {out_dir}")
    print(f"contact list: {contacts_path} (contains personal data, keep it off git)")
    print("The database was not changed.")


if __name__ == "__main__":
    main()
