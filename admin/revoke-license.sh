#!/bin/sh
# Revoke a license. The next online check refuses it. Asks to confirm.
# Usage: admin/revoke-license.sh LICENSE_ID [--yes] [--dry-run]
# Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT) come from .env in the repo root.
. "$(dirname "$0")/_common.sh"
run license_admin.py revoke "$@"
