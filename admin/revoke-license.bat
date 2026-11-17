@echo off
rem Revoke a license. The next online check refuses it. Asks to confirm.
rem Usage: admin\revoke-license.bat LICENSE_ID [--yes] [--dry-run]
rem Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT) come from .env in the repo root.
setlocal
call "%~dp0_common.bat" || exit /b 1
%PY% license_admin.py revoke %*
set RC=%errorlevel%
popd
exit /b %RC%
