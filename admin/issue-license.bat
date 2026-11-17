@echo off
rem Issue a signed license file and register it in the license store (Firestore from .env).
rem Usage: admin\issue-license.bat --customer "Example Ltd" --application QuellDAP --client-email a@b.com ^
rem          --plan gated --features tier-2 --expires-days 365 [--dry-run]
rem The signing key: --key-file PATH or --key-secret NAME, else LICENSE_SIGNING_KEY_FILE or
rem LICENSE_SECRET_NAME (default license-signing-key) from the environment or .env.
rem A cloud secret needs its CLI installed and signed in (gcloud, aws or az).
rem Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT, LICENSE_KID, LICENSE_ISSUER_URL) come from .env.
setlocal
call "%~dp0_common.bat" || exit /b 1
if "%~1"=="" goto help
%PY% issue_license.py %*
goto done
:help
%PY% issue_license.py --help
:done
set RC=%errorlevel%
popd
exit /b %RC%
