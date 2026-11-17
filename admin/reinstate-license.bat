@echo off
rem Set a revoked license back to active. Asks to confirm.
rem Usage: admin\reinstate-license.bat LICENSE_ID [--yes] [--dry-run]
rem Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT) come from .env in the repo root.
setlocal
call "%~dp0_common.bat" || exit /b 1
%PY% license_admin.py reinstate %*
set RC=%errorlevel%
popd
exit /b %RC%
