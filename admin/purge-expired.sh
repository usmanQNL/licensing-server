#!/bin/sh
# Delete licenses (and their installs) that expired more than 30 days ago. Asks to confirm.
# Usage: admin/purge-expired.sh [--dry-run] [--yes]
# Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT) come from .env in the repo root.
. "$(dirname "$0")/_common.sh"
run purge_expired.py "$@"
