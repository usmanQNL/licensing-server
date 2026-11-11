#!/bin/sh
# Checks the required files, then builds and runs the licensing server.
# Usage: ./DockerBuild.sh [image-name]   (run from the folder with the Dockerfile)
#
# The signing key is never stored in this folder. It is read from one of:
#   1. LICENSE_SIGNING_KEY_FILE   a PEM file outside the project, e.g. ~/.config/licensing/private.pem
#   2. LICENSE_KEY_SOURCE         gcloud (default), aws or azure. The key is fetched into a temp file
#                                 that is deleted when the script exits. See README, "Signing key for local builds".
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

KEY_TMP=""
cleanup() { [ -n "$KEY_TMP" ] && rm -f "$KEY_TMP"; return 0; }
trap cleanup EXIT INT TERM

SECRET_NAME="${LICENSE_SECRET_NAME:-license-signing-key}"
if [ -n "${LICENSE_SIGNING_KEY_FILE:-}" ]; then
  KEY_PATH="$LICENSE_SIGNING_KEY_FILE"
  [ -f "$KEY_PATH" ] || { echo "ERROR: LICENSE_SIGNING_KEY_FILE does not exist: $KEY_PATH" >&2; exit 1; }
else
  KEY_TMP="$(mktemp)"
  chmod 600 "$KEY_TMP"
  case "${LICENSE_KEY_SOURCE:-gcloud}" in
    gcloud)
      : "${LICENSE_GCP_PROJECT:?set LICENSE_GCP_PROJECT to your Google Cloud project ID}"
      gcloud secrets versions access latest --secret "$SECRET_NAME" --project "$LICENSE_GCP_PROJECT" > "$KEY_TMP" ;;
    aws)
      aws secretsmanager get-secret-value --secret-id "$SECRET_NAME" --query SecretString --output text > "$KEY_TMP" ;;
    azure)
      : "${LICENSE_AZURE_VAULT:?set LICENSE_AZURE_VAULT to your Key Vault name}"
      az keyvault secret show --vault-name "$LICENSE_AZURE_VAULT" --name "$SECRET_NAME" --query value -o tsv > "$KEY_TMP" ;;
    *) echo "ERROR: LICENSE_KEY_SOURCE must be gcloud, aws or azure" >&2; exit 1 ;;
  esac
  KEY_PATH="$KEY_TMP"
fi
case "$KEY_PATH" in /*) ;; *) KEY_PATH="$(pwd)/$KEY_PATH" ;; esac
grep -q "BEGIN PRIVATE KEY" "$KEY_PATH" || { echo "ERROR: the signing key is empty or not a PEM private key" >&2; exit 1; }

docker build -t "$IMAGE" .
# Mount the signing key (and the Firestore key file, if .env names one) at run time.
set -- -v "$KEY_PATH:/srv/private.pem:ro"
if grep -q '^GOOGLE_APPLICATION_CREDENTIALS=' .env 2>/dev/null; then
  [ -f gcp-sa.json ] || { echo "ERROR: .env sets GOOGLE_APPLICATION_CREDENTIALS but gcp-sa.json is missing" >&2; exit 1; }
  set -- "$@" -v "$(pwd)/gcp-sa.json:/srv/gcp-sa.json:ro"
fi
# Not 'exec': the shell must stay alive so the temp key file is deleted afterwards.
docker run --rm -p 8080:8080 --env-file .env "$@" "$IMAGE"
