@echo off
rem Sign keys.json with the offline root key into keylist.json. Run on your own PC only.
rem Usage: admin\sign-keylist.bat [--revoked k0 ...]
rem Defaults: --root-key-file keys\root_private.pem --keys keys.json --out keylist.json (pass any of them to override).
rem Then put keylist.json next to the Dockerfile and redeploy, BEFORE issuing licenses with a new kid.
setlocal
call "%~dp0_common.bat" || exit /b 1
%PY% sign_keylist.py sign --root-key-file keys\root_private.pem --keys keys.json --out keylist.json %*
set RC=%errorlevel%
popd
exit /b %RC%
