@echo off
rem Reissue every active license with a new signing key (key rotation). Writes files only; the store is not changed.
rem Usage: admin\regenerate-licenses.bat --new-kid k2 (--key-file PATH | --key-secret NAME) [--application NAME] [--issuer-url URL] [--dry-run]
rem Settings (LICENSE_STORAGE, LICENSE_FIRESTORE_PROJECT) come from .env. A cloud secret needs its CLI installed and signed in.
setlocal
call "%~dp0_common.bat" || exit /b 1
%PY% regenerate_licenses.py %*
set RC=%errorlevel%
popd
exit /b %RC%
