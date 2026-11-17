@echo off
rem Delete licenses (and their installs) that expired more than 30 days ago. Asks to confirm.
rem Usage: admin\purge-expired.bat [--dry-run] [--yes]
rem Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT) come from .env in the repo root.
setlocal
call "%~dp0_common.bat" || exit /b 1
%PY% purge_expired.py %*
set RC=%errorlevel%
popd
exit /b %RC%
