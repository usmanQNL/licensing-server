# Shared setup for the admin/*.sh scripts. Not run on its own.
# Runs from the repo root, so .env, keylist.json and licenses/ are found there, and relative paths
# you pass (--out, --key-file) are relative to the repo root.
# Runs only inside a Python virtual environment: the active one ($VIRTUAL_ENV), else .venv/ or venv/
# in the repo root. Without one, or without the dependencies, it stops and runs nothing.
ROOT="$(cd "$(dirname "$0")/.." && pwd)" || exit 1
cd "$ROOT" || exit 1
PY=""
for candidate in "${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}" .venv/bin/python venv/bin/python; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then PY="$candidate"; break; fi
done
if [ -z "$PY" ]; then
  echo "ERROR: no Python virtual environment found in $ROOT, so nothing was run." >&2
  echo "Create one in the repo folder:" >&2
  echo "  python3 -m venv .venv" >&2
  echo "  .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
"$PY" admin/_check_env.py || exit 1
if [ ! -f .env ]; then
  echo "warning: no .env in $ROOT. Copy .env.example to .env and set LICENSE_STORAGE and LICENSE_FIRESTORE_PROJECT." >&2
fi
run() { exec "$PY" "$@"; }
