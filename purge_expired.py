#!/usr/bin/env python3
"""Delete license and install records that expired more than 30 days ago (privacy retention).

Lists the records first. Nothing is deleted until you confirm, unless you pass --yes.
Run with --dry-run to see what would go.

  python purge_expired.py --firestore-project my-project --dry-run
  python purge_expired.py --json-path dev-data.json
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.storage import build_admin_storage  # noqa: E402

RETENTION_AFTER_EXPIRY = timedelta(days=30)


def parse_time(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def main():
    p = argparse.ArgumentParser(description="Delete records kept more than 30 days after expiry.")
    backend = p.add_mutually_exclusive_group()
    backend.add_argument("--firestore-project", help="Google Cloud project ID (Firestore backend).")
    backend.add_argument("--json-path", help="License JSON file (JSON backend).")
    p.add_argument("--dry-run", action="store_true", help="List what would be deleted. Delete nothing.")
    p.add_argument("--yes", action="store_true", help="Skip the confirmation prompt (for scripts).")
    args = p.parse_args()

    store = build_admin_storage(args.firestore_project, args.json_path)
    now = datetime.now(timezone.utc)
    due = []
    for doc in store.list_licenses():
        expires = parse_time(doc.get("expires_at"))
        if expires and now - expires > RETENTION_AFTER_EXPIRY:
            due.append(doc["license_id"])

    if not due:
        print("nothing to delete")
        return
    print(f"{len(due)} license(s) expired more than 30 days ago:")
    for license_id in due:
        print(f"  {license_id}")

    if args.dry_run:
        print("dry run: nothing deleted")
        return
    if not args.yes:
        answer = input(f"Delete these {len(due)} license(s) and their install records? Type DELETE to confirm: ")
        if answer.strip() != "DELETE":
            sys.exit("cancelled, nothing deleted")

    for license_id in due:
        store.delete_license(license_id)
        print(f"deleted {license_id}")


if __name__ == "__main__":
    main()
