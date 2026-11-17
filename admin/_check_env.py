"""Run by admin/_common.bat and admin/_common.sh before any admin script.

Stops unless this Python is a virtual environment that has the admin scripts' dependencies.
"""
import importlib.util
import sys

FIX_WIN = "  .venv\\Scripts\\pip install -r requirements.txt"
FIX_NIX = "  .venv/bin/pip install -r requirements.txt"
fix = FIX_WIN if sys.platform == "win32" else FIX_NIX

if sys.prefix == sys.base_prefix:
    sys.exit(f"ERROR: {sys.executable} is not a virtual environment, so nothing was run.\n"
             "Create one in the repo folder:\n  python -m venv .venv\n" + fix)

needed = {"cryptography": "cryptography", "google.cloud.firestore": "google-cloud-firestore"}
missing = []
for module, package in needed.items():
    try:
        found = importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:  # parent package (google, google.cloud) missing
        found = False
    if not found:
        missing.append(package)
if missing:
    sys.exit(f"ERROR: the virtual environment {sys.prefix} is missing {', '.join(missing)}, so nothing was run.\n"
             "Install the dependencies:\n" + fix)
