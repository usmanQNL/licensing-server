@echo off
rem Checks the required files, then builds and runs the licensing server.
rem Usage: DockerBuild.bat [image-name]   (run from the folder with the Dockerfile)
rem
rem The signing key is never stored in this folder. It is read from one of:
rem   1. LICENSE_SIGNING_KEY_FILE   a PEM file outside the project, e.g. %USERPROFILE%\.config\licensing\private.pem
rem   2. LICENSE_KEY_SOURCE         gcloud (default), aws or azure. The key is fetched into a temp file
rem                                 that is deleted afterwards. See README, "Signing key for local builds".
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

if not defined LICENSE_SECRET_NAME set LICENSE_SECRET_NAME=license-signing-key
set TEMP_KEY=
if defined LICENSE_SIGNING_KEY_FILE (
  set KEY_PATH=%LICENSE_SIGNING_KEY_FILE%
  if not exist "%LICENSE_SIGNING_KEY_FILE%" (
    echo ERROR: LICENSE_SIGNING_KEY_FILE does not exist: %LICENSE_SIGNING_KEY_FILE%
    exit /b 1
  )
  goto have_key
)
if not defined LICENSE_KEY_SOURCE set LICENSE_KEY_SOURCE=gcloud
set KEY_PATH=%TEMP%\license-signing-key-%RANDOM%.pem
set TEMP_KEY=1
if /i "%LICENSE_KEY_SOURCE%"=="gcloud" (
  if not defined LICENSE_GCP_PROJECT (echo ERROR: set LICENSE_GCP_PROJECT & exit /b 1)
  gcloud secrets versions access latest --secret %LICENSE_SECRET_NAME% --project %LICENSE_GCP_PROJECT% > "%KEY_PATH%"
) else if /i "%LICENSE_KEY_SOURCE%"=="aws" (
  aws secretsmanager get-secret-value --secret-id %LICENSE_SECRET_NAME% --query SecretString --output text > "%KEY_PATH%"
) else if /i "%LICENSE_KEY_SOURCE%"=="azure" (
  if not defined LICENSE_AZURE_VAULT (echo ERROR: set LICENSE_AZURE_VAULT & exit /b 1)
  az keyvault secret show --vault-name %LICENSE_AZURE_VAULT% --name %LICENSE_SECRET_NAME% --query value -o tsv > "%KEY_PATH%"
) else (
  echo ERROR: LICENSE_KEY_SOURCE must be gcloud, aws or azure
  exit /b 1
)
if errorlevel 1 (
  echo ERROR: could not fetch the signing key
  if exist "%KEY_PATH%" del "%KEY_PATH%"
  exit /b 1
)
:have_key
findstr /c:"BEGIN PRIVATE KEY" "%KEY_PATH%" >nul 2>&1
if errorlevel 1 (
  echo ERROR: the signing key is empty or not a PEM private key
  if defined TEMP_KEY del "%KEY_PATH%" 2>nul
  exit /b 1
)

set GCP_MOUNT=
findstr /b /c:"GOOGLE_APPLICATION_CREDENTIALS=" .env >nul 2>&1
if not errorlevel 1 (
  if not exist gcp-sa.json (
    echo ERROR: .env sets GOOGLE_APPLICATION_CREDENTIALS but gcp-sa.json is missing
    if defined TEMP_KEY del "%KEY_PATH%" 2>nul
    exit /b 1
  )
  set GCP_MOUNT=-v "%cd%\gcp-sa.json:/srv/gcp-sa.json:ro"
)
docker build -t %IMAGE% .
if errorlevel 1 (
  if defined TEMP_KEY del "%KEY_PATH%" 2>nul
  exit /b 1
)
docker run --rm -p 8080:8080 --env-file .env -v "%KEY_PATH%:/srv/private.pem:ro" %GCP_MOUNT% %IMAGE%
set RC=%errorlevel%
if defined TEMP_KEY del "%KEY_PATH%" 2>nul
exit /b %RC%
