#!/bin/sh
# Set a revoked license back to active. Asks to confirm.
# Usage: admin/reinstate-license.sh LICENSE_ID [--yes] [--dry-run]
# Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT) come from .env in the repo root.
. "$(dirname "$0")/_common.sh"
run license_admin.py reinstate "$@"
