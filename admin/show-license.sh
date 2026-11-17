#!/bin/sh
# Show every stored field of one license.
# Usage: admin/show-license.sh LICENSE_ID
# Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT) come from .env in the repo root.
. "$(dirname "$0")/_common.sh"
run license_admin.py show "$@"
