@echo off
rem List licenses: id, status, plan, application, customer, expiry.
rem Usage: admin\list-licenses.bat [--status active|revoked] [--application NAME]
rem Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT) come from .env in the repo root.
setlocal
call "%~dp0_common.bat" || exit /b 1
%PY% license_admin.py list %*
set RC=%errorlevel%
popd
exit /b %RC%
