"""Loads settings from a .env file in the repo root, so scripts and the server need no env flags.

Real environment variables always win over .env. Cloud Run ignores this file: set the same
variables on the service with `gcloud run deploy --set-env-vars` (see README).
"""
import os


def _load_dotenv(path: str) -> None:
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
