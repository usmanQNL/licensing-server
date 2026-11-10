@echo off
rem Checks the required files, then builds and runs the licensing server.
rem Usage: start.bat [image-name]   (run from the folder with the Dockerfile)
setlocal
set IMAGE=%~1
if "%IMAGE%"=="" set IMAGE=license-check
set missing=0
for %%F in (Dockerfile keylist.json root-public.pem .env) do (
  if not exist "%%F" (
    echo ERROR: missing file: %%F
    set missing=1
  )
)
if "%missing%"=="1" (
  echo Aborted. See README, "Files needed to build".
  exit /b 1
)
if not exist private.pem (
  echo ERROR: missing file: private.pem ^(the signing key^)
  exit /b 1
)
set GCP_MOUNT=
findstr /b /c:"GOOGLE_APPLICATION_CREDENTIALS=" .env >nul 2>&1
if not errorlevel 1 (
  if not exist gcp-sa.json (
    echo ERROR: .env sets GOOGLE_APPLICATION_CREDENTIALS but gcp-sa.json is missing
    exit /b 1
  )
  set GCP_MOUNT=-v "%cd%\gcp-sa.json:/srv/gcp-sa.json:ro"
)
docker build -t %IMAGE% .
if errorlevel 1 exit /b 1
docker run --rm -p 8080:8080 --env-file .env -v "%cd%\private.pem:/srv/private.pem:ro" %GCP_MOUNT% %IMAGE%
