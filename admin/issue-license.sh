#!/bin/sh
# Issue a signed license file and register it in the license store (Firestore from .env).
# Usage: admin/issue-license.sh --customer "Example Ltd" --application QuellDAP --client-email a@b.com \
#          --plan gated --features tier-2 --expires-days 365 [--dry-run]
# The signing key: --key-file PATH or --key-secret NAME, else LICENSE_SIGNING_KEY_FILE or
# LICENSE_SECRET_NAME (default license-signing-key) from the environment or .env.
# A cloud secret needs its CLI installed and signed in (gcloud, aws or az).
# Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT, LICENSE_KID, LICENSE_ISSUER_URL) come from .env.
. "$(dirname "$0")/_common.sh"
[ $# -eq 0 ] && set -- --help
run issue_license.py "$@"
