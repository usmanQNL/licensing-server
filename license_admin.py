#!/usr/bin/env python3
"""Manage licenses: list, show, revoke and reinstate (SPEC.md section 6).

Pick the backend with --firestore-project P (Firestore) or --json-path FILE (JSON file).
Any NoSQL database works by adding an adapter in app/storage.py.

Examples:
  python license_admin.py --firestore-project P list
  python license_admin.py --json-path dev-data.json show LIC-20261110-ABC123
  python license_admin.py --firestore-project P revoke LIC-20261110-ABC123

`revoke` and `reinstate` ask for confirmation unless --yes is given. Add --dry-run to see what would change.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.storage import build_admin_storage  # noqa: E402


def set_status(store, license_id, status, args):
    doc = store.get_license(license_id)
    if doc is None:
        sys.exit(f"error: no license {license_id}")
    print(f"{license_id}: {doc.get('status')} -> {status}")
    if args.dry_run:
        print("dry run: nothing changed")
        return
    if not args.yes:
        answer = input(f"Set {license_id} to {status}? [y/N] ").strip().lower()
        if answer != "y":
            sys.exit("cancelled")
    store.set_license_status(license_id, status)
    print("done. The next online check picks this up.")


def main():
    p = argparse.ArgumentParser(description="Manage licenses.")
    backend = p.add_mutually_exclusive_group()
    backend.add_argument("--firestore-project", help="Google Cloud project ID (Firestore backend).")
    backend.add_argument("--json-path", help="License JSON file (JSON backend, local use).")
    p.add_argument("--dry-run", action="store_true", help="Show what would change, change nothing.")
    p.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List licenses and their status.")
    sub.add_parser("show", help="Show one license.").add_argument("license_id")
    sub.add_parser("revoke", help="Set status to revoked.").add_argument("license_id")
    sub.add_parser("reinstate", help="Set status back to active.").add_argument("license_id")
    args = p.parse_args()

    store = build_admin_storage(args.firestore_project, args.json_path)
    if args.command == "list":
        for d in store.list_licenses():
            print(f"{d['license_id']}\t{d.get('status')}\t{d.get('plan')}\t{d.get('application', '')}\t{d.get('customer', '')}")
    elif args.command == "show":
        doc = store.get_license(args.license_id)
        if doc is None:
            sys.exit(f"error: no license {args.license_id}")
        print(doc)
    elif args.command == "revoke":
        set_status(store, args.license_id, "revoked", args)
    elif args.command == "reinstate":
        set_status(store, args.license_id, "active", args)


if __name__ == "__main__":
    main()
