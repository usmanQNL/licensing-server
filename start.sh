#!/bin/sh
# Checks the required files, then builds and runs the licensing server.
# Usage: ./start.sh [image-name]   (run from the folder with the Dockerfile)
set -e
IMAGE="${1:-license-check}"
missing=0
for f in Dockerfile keylist.json root-public.pem .env; do
  if [ ! -f "$f" ]; then
    echo "ERROR: missing file: $f (expected in $(pwd))" >&2
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  echo "Aborted. See README, 'Files needed to build'." >&2
  exit 1
fi
docker build -t "$IMAGE" .
# Mount the signing key (and the Firestore key file, if .env names one) at run time.
set -- -v "$(pwd)/private.pem:/srv/private.pem:ro"
if grep -q '^GOOGLE_APPLICATION_CREDENTIALS=' .env 2>/dev/null; then
  [ -f gcp-sa.json ] || { echo "ERROR: .env sets GOOGLE_APPLICATION_CREDENTIALS but gcp-sa.json is missing" >&2; exit 1; }
  set -- "$@" -v "$(pwd)/gcp-sa.json:/srv/gcp-sa.json:ro"
fi
[ -f private.pem ] || { echo "ERROR: missing file: private.pem (the signing key)" >&2; exit 1; }
exec docker run --rm -p 8080:8080 --env-file .env "$@" "$IMAGE"
