@echo off
rem Show every stored field of one license.
rem Usage: admin\show-license.bat LICENSE_ID
rem Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT) come from .env in the repo root.
setlocal
call "%~dp0_common.bat" || exit /b 1
%PY% license_admin.py show %*
set RC=%errorlevel%
popd
exit /b %RC%
