#!/bin/sh
# List licenses: id, status, plan, application, customer, expiry.
# Usage: admin/list-licenses.sh [--status active|revoked] [--application NAME]
# Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT) come from .env in the repo root.
. "$(dirname "$0")/_common.sh"
run license_admin.py list "$@"
