# Builds the licensing server. Put these files in the same folder as this Dockerfile:
#   keylist.json       your signed key list (made with sign_keylist.py)
#   root-public.pem    the root public key
#   .env               settings (copied into the image; keep secrets out of it)
# Usage: use start.bat (Windows) or start.sh (Linux/Mac), which check the files first.
# Or build by hand: docker build -t license-check .

ARG REPO_REF=master

# Stage 1: fetch the server code from GitHub.
FROM alpine/git AS src
ARG REPO_REF
RUN git clone --depth 1 --branch "${REPO_REF}" https://github.com/usmanQNL/licensing-server.git /src \
 && rm -rf /src/.git

# Stage 2: the runtime image.
FROM python:3.12-slim
WORKDIR /srv
COPY --from=src /src/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=src /src/app ./app
# Your files from this folder. The build stops with "not found" if any is missing.
COPY keylist.json ./keylist.json
COPY root-public.pem ./root-public.pem
COPY .env ./.env
ENV PORT=8080
ENV LICENSE_KEYLIST_PATH=/srv/keylist.json
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
