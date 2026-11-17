#!/bin/sh
# Sign keys.json with the offline root key into keylist.json. Run on your own PC only.
# Usage: admin/sign-keylist.sh [--revoked k0 ...]
# Defaults: --root-key-file keys/root_private.pem --keys keys.json --out keylist.json (pass any of them to override).
# Then put keylist.json next to the Dockerfile and redeploy, BEFORE issuing licenses with a new kid.
. "$(dirname "$0")/_common.sh"
run sign_keylist.py sign --root-key-file keys/root_private.pem --keys keys.json --out keylist.json "$@"
