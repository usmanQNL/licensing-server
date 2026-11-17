# Shared setup for the admin/*.sh scripts. Not run on its own.
# Runs from the repo root, so .env, keylist.json and licenses/ are found there, and relative paths
# you pass (--out, --key-file) are relative to the repo root.
# Python: $PYTHON if set, else .venv/bin/python, else python3, else python.
ROOT="$(cd "$(dirname "$0")/.." && pwd)" || exit 1
cd "$ROOT" || exit 1
if [ -n "${PYTHON:-}" ]; then PY="$PYTHON"
elif [ -x .venv/bin/python ]; then PY=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then PY=python3
else PY=python
fi
if [ ! -f .env ]; then
  echo "warning: no .env in $ROOT. Copy .env.example to .env and set LICENSE_STORAGE and LICENSE_FIRESTORE_PROJECT." >&2
fi
run() { exec "$PY" "$@"; }
