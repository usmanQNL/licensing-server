"""Server-side Licensing Gate for a FastAPI app. This is the check that can't be bypassed from the browser.

The server holds the installed license file. A route that needs a paid feature declares
`Depends(require_feature("..."))` and answers HTTP 403 when the license doesn't include it.
`GET /license/plan` returns the plan JSON, so a React or vanilla JS frontend can show or hide UI
from the server's answer instead of checking the license itself.

Run (needs fastapi and uvicorn, already in requirements.txt):
    cd samples/python
    uvicorn server_fastapi:app --port 8000
Settings (environment variables, defaults are the demo files):
    APP_NAME (default Demo) and <APP_NAME>_LICENSE_FILE (from the environment or ./.env,
    relative to the folder you start the server in), LICENSE_PUBLIC_KEY, LICENSE_FEATURES
    For example APP_NAME=QuellDAP reads QUELLDAP_LICENSE_FILE=licensing/quelldap.license.json from .env.
"""
import json
import os

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from licensing import license_file_env_var, read_dotenv
from plan import DEMO, _read, license_plan


def _license_file():
    # The project's .env holds the license location as <APP_NAME>_LICENSE_FILE (a path relative to the
    # project root). A real environment variable wins. Unset: the demo license.
    var = license_file_env_var(os.environ.get("APP_NAME", "Demo"))
    rel = os.environ.get(var) or read_dotenv(".env").get(var)
    return os.path.abspath(rel) if rel else os.path.join(DEMO, "license-gated.json")


LICENSE_FILE = _license_file()
PUBLIC_KEY = _read(os.environ.get("LICENSE_PUBLIC_KEY", os.path.join(DEMO, "demo-public.pem")))
ALL_FEATURES = json.loads(_read(os.environ.get("LICENSE_FEATURES", os.path.join(DEMO, "features.json"))))


def current_plan():
    # Read and verify on every call, so a replaced license file or an expiry takes effect
    # without a restart. Verifying one Ed25519 signature takes microseconds.
    return license_plan(_read(LICENSE_FILE), PUBLIC_KEY, ALL_FEATURES)


class FeatureNotLicensed(Exception):
    def __init__(self, feature, reason):
        self.feature, self.reason = feature, reason


def require_feature(feature):
    """FastAPI dependency: HTTP 403 unless the installed license enables `feature`."""
    def check():
        plan = current_plan()
        enabled = next((f["enabled"] for f in plan["features"] if f["name"] == feature), False)
        if not enabled:
            reason = "the license does not include this feature" if plan["valid"] else plan["reason"]
            raise FeatureNotLicensed(feature, reason)
    return check


app = FastAPI()


@app.exception_handler(FeatureNotLicensed)
def not_licensed(request: Request, exc: FeatureNotLicensed):
    return JSONResponse({"error": "feature_not_licensed", "feature": exc.feature, "reason": exc.reason}, status_code=403)


@app.get("/license/plan")
def get_plan():
    return current_plan()


@app.get("/reports/pdf", dependencies=[Depends(require_feature("export_pdf"))])
def export_pdf():
    return {"ok": True, "message": "PDF export ran"}


@app.get("/auth/sso", dependencies=[Depends(require_feature("sso"))])
def sso():
    return {"ok": True, "message": "SSO is available"}


@app.get("/health")
def health():
    return {"ok": True}  # free routes need no gate
