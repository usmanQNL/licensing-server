@echo off
rem Shared setup for the admin\*.bat scripts. Not run on its own: each script calls it, then popd.
rem Runs from the repo root, so .env, keylist.json and licenses\ are found there, and relative paths
rem you pass (--out, --key-file) are relative to the repo root.
rem Python: %PYTHON% if set, else .venv\Scripts\python.exe, else python.
pushd "%~dp0.." || exit /b 1
if defined PYTHON (
  set PY="%PYTHON%"
) else if exist ".venv\Scripts\python.exe" (
  set PY="%CD%\.venv\Scripts\python.exe"
) else (
  set PY=python
)
if not exist ".env" echo warning: no .env in %CD%. Copy .env.example to .env and set LICENSE_STORAGE and LICENSE_FIRESTORE_PROJECT. 1>&2
exit /b 0
