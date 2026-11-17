@echo off
rem Shared setup for the admin\*.bat scripts. Not run on its own: each script calls it, then popd.
rem Runs from the repo root, so .env, keylist.json and licenses\ are found there, and relative paths
rem you pass (--out, --key-file) are relative to the repo root.
rem Runs only inside a Python virtual environment: the active one (VIRTUAL_ENV), else .venv\ or venv\
rem in the repo root. Without one, or without the dependencies, it stops and runs nothing.
pushd "%~dp0.." || exit /b 1
set PY=
if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" set PY="%VIRTUAL_ENV%\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set PY="%CD%\.venv\Scripts\python.exe"
if not defined PY if exist "venv\Scripts\python.exe" set PY="%CD%\venv\Scripts\python.exe"
if not defined PY goto no_venv
%PY% admin\_check_env.py
if errorlevel 1 goto failed
if not exist ".env" echo warning: no .env in %CD%. Copy .env.example to .env and set LICENSE_STORAGE and LICENSE_FIRESTORE_PROJECT. 1>&2
exit /b 0

:no_venv
echo ERROR: no Python virtual environment found in %CD%, so nothing was run. 1>&2
echo Create one in the repo folder: 1>&2
echo   python -m venv .venv 1>&2
echo   .venv\Scripts\pip install -r requirements.txt 1>&2
:failed
popd
exit /b 1
