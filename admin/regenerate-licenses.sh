#!/bin/sh
# Reissue every active license with a new signing key (key rotation). Writes files only; the store is not changed.
# Usage: admin/regenerate-licenses.sh --new-kid k2 (--key-file PATH | --key-secret NAME) [--application NAME] [--issuer-url URL] [--dry-run]
# Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT) come from .env. A cloud secret needs its CLI installed and signed in.
. "$(dirname "$0")/_common.sh"
run regenerate_licenses.py "$@"
