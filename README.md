# Licensing toolkit

Reusable licensing for your projects: signed Ed25519 license files, a daily online check, and a grace period. It includes:

- `SKILL.md`: a Claude skill that walks through adding licensing to a project.
- `issue_license.py`: signs license files and registers them in the storage backend (Firestore or a JSON file).
- `app/`: an online check server (FastAPI), with storage behind an interface. Firestore is the first adapter.
- `verifiers/`: license checks for Python, Node.js, and Rust, with examples. A Dart verifier is included but untested (see below).
- `verifiers/cases.json`: shared test cases that every verifier must pass.

Licensing is a deterrent, not DRM. A check on the user's machine can always be bypassed. Use the online check and revocation to limit the damage.

## Choose a mode

| Mode | What it does |
|---|---|
| OpenSource | Adds an MIT `LICENSE`. No keys, no checks. |
| Subscription | Signed license with an expiry date, checked at launch, with a 14-day grace period. |
| Gated | Signed license listing features. Each paid feature checks its flag. Optional end date, with the same 14-day grace period. |

## Use the skill

Add `SKILL.md` to your Claude skills (claude.ai: Capabilities, then Skills). In a new project, ask Claude to add licensing. It asks for the mode, application name, languages, whether to enable the online check, and feature names. It then walks you through the keys, verifier, feature gating, and tests.

## Manage licenses

`license_admin.py` lists, shows, revokes, and reinstates licenses. Pick the backend with `--firestore-project` or `--json-path`:

```bash
python license_admin.py --firestore-project YOUR_PROJECT list
python license_admin.py --firestore-project YOUR_PROJECT show LIC-...
python license_admin.py --firestore-project YOUR_PROJECT revoke LIC-...      # asks to confirm
python license_admin.py --firestore-project YOUR_PROJECT reinstate LIC-...
```

Add `--dry-run` to see what would change without changing it. Add `--yes` to skip the prompt in scripts.

To preview an issue without writing anything, add `--dry-run` to `issue_license.py`.

## Issue a license

Install the issuer dependencies once:

```bash
pip install google-cloud-firestore cryptography
gcloud auth application-default login   # only if registering in Firestore
```

Issue a license. This reads the private key from Secret Manager, so it never sits on disk:

```bash
python issue_license.py --help

python issue_license.py --customer "Example Ltd" --application QuellDAP --plan subscription \
  --client-email contact@example.com --client-phone "+44 20 0000 0000" \
  --features sso,hourly_sync --expires-days 365 \
  --key-secret license-signing-key --project YOUR_PROJECT \
  --firestore-project YOUR_PROJECT
```

Or use a local key file with `--key-file private.pem`. Keep that file out of git.

The output is `licenses/<application>/<license_id>.license.json`. Send that file to the customer. With `--firestore-project`, the license is also registered in the `licenses` collection with `status` set to `active`. The contact email and phone are stored in the license store only.

`--client-email` is required. `--kid` sets the signing key ID (default `k1`), and `--max-installs` sets the seat limit (default 1). Before writing, the issuer reads `keylist.json` (or `--keylist PATH`) and warns if the kid is missing from it or revoked, so you can upload a new key list first.

Revoke a license by setting its `status` to `revoked` in the Firestore console. The next online check picks it up.

## Key rotation (`kid`)

Each license file and each server reply has a `kid` (key ID) next to the signature. The issuer sets it with `--kid` (default `k1`), and the server sets it with `LICENSE_KID` (default `k1`).

Apps can trust more than one public key. Pass a map of `{kid: PEM}` instead of a single PEM string. The verifier picks the key that matches the file's `kid`.

To rotate:
1. Generate the new key pair and store the private key in Secret Manager (for example `license-signing-key-2`).
2. Ship an app update that trusts both the old and new public keys.
3. Once most users have updated, switch the issuer and server to the new key and `kid`.
4. Remove the old key in a later release.

If a key is compromised, remove it from the app in an emergency release and reissue licenses. Apps on older versions will reject the new licenses.

### Signed key list (rotate without an app update)

Apps trust a signed list of signing keys, so rotating a key needs no app update. Only the root key has to be built into the app. Run every step below on your own PC.

**Step 1: create the root key (once).**
`python sign_keylist.py init-root --out keys/root_private.pem`
This writes two files:
- `keys/root_private.pem`: the root private key. Keep it offline and out of git. If you lose it, apps need an update to trust a new root.
- `root-public.pem`: the root public key. Ship it inside the app.

**Step 2: add your signing key's public half to `keys.json`.**
Get the k1 public key list without writing the private key to disk. Run this in the same shell as the Secret Manager fetch, so the key is never saved to a file:
`gcloud secrets versions access latest --secret license-signing-key --project YOUR_PROJECT | python sign_keylist.py make-keys --kid k1 --key-stdin --out keys.json`
No private key is copied into keys.json.
Repeat with another kid when you rotate, for example `--kid k2`.

**Step 3: sign the key list with the root key.**
`python sign_keylist.py sign --root-key-file keys/root_private.pem --keys keys.json --out keylist.json`
To block a compromised kid, add `--revoked k1` (or whichever kid).

**Step 4: put the files where they're used.**
- `keylist.json` goes next to the Dockerfile, so the image copies it in. For Cloud Run, either rebuild with the new file or mount it from a secret, then set `LICENSE_KEYLIST_PATH`.
- The server serves it at `GET /v1/keys`. Do this before issuing licenses with the new kid.
- `root-public.pem` goes inside the app.

**Step 5: reissue existing licenses after a rotation.**
`python regenerate_licenses.py --firestore-project YOUR_PROJECT --new-kid k2 --key-file private-k2.pem --dry-run`
The database is not changed.

The Python and Node verifiers fetch and cache the list: `load_trusted_keys(root_pem, cache_path=..., endpoint=...)` in Python, and `loadTrustedKeys(rootPem, {cachePath, endpoint})` in Node. Each list is verified with the root key. A list older than the cached one is ignored, so an old list can't undo a revocation. Rust and Dart don't have this yet.

Only the root key needs an app update if it is ever compromised.

## Verify a license in your app

Embed the public key in your app. Never embed the private key. Use the verifier for your language, with the public key PEM.

### Python

```python
from licensing import verify_license

text = open("license.json", encoding="utf-8").read()
public_key = open("license-public.pem", encoding="utf-8").read()

result = verify_license(text, public_key, mode="subscription")
if result.valid_for_paid_features:
    print("Licensed:", result.payload["customer"], result.reason)
else:
    print("Paid features are off:", result.reason)
```

Copy `verifiers/python/licensing.py` into your project. It needs `cryptography`. See `verifiers/python/example.py` for a full script:

```bash
python verifiers/python/example.py path/to/license.json path/to/license-public.pem
```

For a Gated license, use `mode="gated"` and pass the feature the code is about to use. See `verifiers/python/example_gated.py`:

```python
verify_license(text, public_key, mode="gated", features_needed=["online_update"])
```

```bash
python verifiers/python/example_gated.py path/to/gated-license.json path/to/license-public.pem
```

### Rust

`verifiers/rust/` has the full verifier: license files, `kid` key selection, the online reply check, and `evaluate`. It passes the shared cases and the online-reply fixtures. Add it with `cargo add` or copy the crate, and run `cargo test`.

### Dart and Flutter (available, untested)

`verifiers/dart/licensing.dart` is available, but it has not been tested. It was written without a Dart SDK. It uses the `cryptography` package. Before you ship it, run the shared cases in `verifiers/cases.json` with `dart test` and fix any failures.

### Node.js

```js
const fs = require('fs');
const { verifyLicense } = require('./licensing');

const text = fs.readFileSync('license.json', 'utf8');
const publicKey = fs.readFileSync('license-public.pem', 'utf8');

const result = verifyLicense(text, publicKey, 'subscription');
if (result.valid) {
  console.log('Licensed:', result.payload.customer, result.reason);
} else {
  console.log('Paid features are off:', result.reason);
}
```

Copy `verifiers/node/licensing.js` into your project. It uses only Node's built-in crypto. See `verifiers/node/example.js` for a full script:

```bash
node verifiers/node/example.js path/to/license.json path/to/license-public.pem
```

For a Gated license, use `'gated'` and pass the feature. See `verifiers/node/example_gated.js`:

```js
verifyLicense(text, publicKey, 'gated', { featuresNeeded: ['online_update'] });
```

```bash
node verifiers/node/example_gated.js path/to/gated-license.json path/to/license-public.pem
```

Both verifiers return `valid`, `reason`, `payload`, and whether the license is in its grace period. They never throw for bad license input.

### Plan and gate samples

Ready-made **Licensing Plan** (plan details as JSON) and **Licensing Gate** (`true`/`false` for one feature) scripts are in [`samples/`](samples/README.md):

- [React](samples/react/LicenseChecks.jsx)
- [Vanilla JS](samples/vanilla-js/license-checks.js)
- [Python](samples/python/plan.py) ([gate](samples/python/gate.py))
- [Ruby](samples/ruby/plan.rb) ([gate](samples/ruby/gate.rb))
- [Rust](samples/rust/src/bin/plan.rs) ([gate](samples/rust/src/bin/gate.rs))
- [curl](samples/curl/plan.sh) ([gate](samples/curl/gate.sh))

Server-side gates, which refuse a paid route with HTTP 403 and can't be bypassed from the browser: [FastAPI](samples/python/server_fastapi.py), [Express](samples/node/server_express.js) (backend for React and vanilla JS), [Rack](samples/ruby/license_gate_middleware.rb) and [axum](samples/rust/server/src/main.rs). See [Server-side gate](samples/README.md#server-side-gate-the-one-that-cant-be-bypassed).

## Online check

If your app calls the server once a day, the signed reply tells it whether the license is `active`, `revoked`, `unknown`, or `limit_reached`:

```bash
curl -s -X POST "https://YOUR_SERVICE_URL/v1/check" \
  -H "Content-Type: application/json" \
  -d '{"license_id":"LIC-...","install_hash":"a-random-id-per-install"}'
```

For one decision that combines the license and the online check, call `evaluate` (Python) or `evaluate` (Node). It returns off when the local license is invalid, or when a fresh reply says `revoked`, `unknown`, or `limit_reached`. With no reply, or a reply past `valid_until`, the local license decides, so offline use keeps working.

To check the reply on its own, use `check_online_reply` (Python) or `checkOnlineReply` (Node) from the verifiers. They check the reply's signature, the license ID, and `valid_until`. Cache the last reply text yourself, and reuse it when the server is unreachable, until `valid_until` passes.

**Install tokens:** the first check from a new install returns an `install_token` once, in the signed reply. Store it, and send it as `install_token` on every later check. A check for a known install without the right token gets HTTP 403.

**Clock guard:** store the newest time the app has seen, and pass it to `evaluate` (or `check_online_reply`) as `last_seen`. If the clock moves back more than 5 minutes, paid features turn off until the clock is corrected.

Statuses:
- `active`: paid features stay on.
- `revoked` or `unknown`: paid features turn off at the next successful check.
- `limit_reached`: this install is beyond the license's seat limit, so paid features turn off.

Sign-in is never blocked.

**Seat limits:** each license has `max_installs` (default 1). The server counts distinct install hashes. Once the limit is reached, a new install gets `limit_reached`. Issue a license with `--max-installs N` to allow more installs.

Let users turn the online check off in settings.

## Privacy and data retention

What the server stores:
- `licenses`: license ID, customer name, contact email and phone (when given), application, plan, features, seat limit, dates, and status.
- `installs`: license ID, a random install ID (`install_hash`), first and last seen times, and a SHA-256 hash of the install token. It never stores the token itself.

What it doesn't store: names, emails, IP addresses, or machine identifiers. Customer names are only in the `licenses` records you create.

What is logged: the hosting platform keeps request logs, which include client IP addresses and the path. The app logs only rate-limited IPs. Set a retention period in your platform (for example, 30 days for Cloud Run logs) and tell customers what you keep.

Retention for installs: delete install records for licenses that have ended. In Firestore, you can set a TTL policy on the `last_seen` field of `installs` (Firestore console: Time-to-live).

Retention policy (for customers and your records):
- License records and install records are kept for as long as the license is valid.
- After the license expires, they are kept for another 30 days, then deleted completely.
- Contact details (`client_email`, `client_phone`) are kept on the same schedule, and are never written to license files or server replies.
- Run `python purge_expired.py --firestore-project YOUR_PROJECT --dry-run` to list records past the 30 days. Run it without `--dry-run` to delete them. It asks you to type DELETE first. Run it on a schedule if you want it automatic.
- To delete one record when a customer asks, delete the license and its install records in the Firestore console.

Tell customers that the daily check sends the license ID and a random install ID to your server, and that you keep the records above, including their contact details, under the retention policy above.

## Known limits

- A leaked license file can still use up seats, since the file is the only thing a customer holds. Install tokens stop spoofing, not leaks. To free a seat, delete the install document in Firestore (or the JSON file). Consider a reset process for customers.
- Installs created before install tokens existed have no token, so they get HTTP 403. Delete their install document so they activate again and get a token.
- Rate limits are per instance, and the client IP comes from the last `X-Forwarded-For` entry. Add platform-level limits (Cloud Armor, AWS WAF, or similar) for a global cap.

## Use another database

The server and the scripts talk to storage through one small interface, in `app/storage.py`. Any NoSQL database works if you implement these methods. The scripts (`issue_license.py`, `license_admin.py`, `regenerate_licenses.py`, `purge_expired.py`) use the same interface, so they work with any backend:

| Method | What it does |
|---|---|
| `get_license(license_id)` | Return the license document as a dict, or `None`. |
| `get_install(license_id, install_hash)` | Return the install record (including `token_hash`), or `None`. |
| `save_install(license_id, install_hash, seen_at, token_hash=None)` | Create or update the install. Keep `first_seen` on updates. Store `token_hash` when given. |
| `set_license_status(license_id, status)` | Set `active` or `revoked`. |
| `count_installs(license_id)` | Count distinct install hashes for the license. |
| `list_licenses(status=None, application=None)` | Return license documents (each with `license_id`), optionally filtered. Used by the admin scripts. |
| `put_license(license_id, doc)` | Create or replace a license document. Used by `issue_license.py`. |
| `delete_license(license_id)` | Delete a license and its install records. Used by `purge_expired.py`. |

Steps:
1. Subclass `Storage` in `app/storage.py`, and implement all eight methods. Use the `JsonStorage` and `FirestoreStorage` classes as examples.
2. Add a branch to `build_storage()` for your new name, for example `LICENSE_STORAGE=postgres`.
3. Store the connection details in environment variables, not in code.
4. Store installs with a unique key on `(license_id, install_hash)`, so a repeat check doesn't create a second seat.
5. Add a test in `tests/test_server.py` for your backend, reusing the seat-limit test.

Example: Postgres with `psycopg` (sketch, not tested):

```python
class PostgresStorage(Storage):
    def __init__(self, dsn):
        import psycopg
        self.conn = psycopg.connect(dsn, autocommit=True)

    def get_license(self, license_id):
        row = self.conn.execute(
            "SELECT license_id, status, plan, customer, max_installs FROM licenses WHERE license_id = %s",
            (license_id,)).fetchone()
        return dict(zip(["license_id", "status", "plan", "customer", "max_installs"], row)) if row else None
    # ...implement the other four methods the same way
```

Works with any SQL database. For DynamoDB, Cosmos DB, or MongoDB, use the same eight methods with that database's client.

## Run on other cloud platforms

The server reads only environment variables and mounted files, so it runs on any cloud. Each platform supplies the same settings in its own way:

| Need | Google Cloud | Azure | AWS | DigitalOcean or any host |
|---|---|---|---|---|
| Database | `LICENSE_STORAGE=firestore` | `cosmos` (stub) | `dynamodb` (stub) | `postgres` (stub, `DATABASE_URL`) |
| Database login | Application Default Credentials | `COSMOS_ENDPOINT`, `COSMOS_KEY` | default AWS credential chain (IAM role) | `DATABASE_URL` |
| Signing key | Secret Manager, mounted as a file | Key Vault, mounted as a file | Secrets Manager, mounted as a file | env var or file |
| Deploy | `gcloud run deploy --source .` | `az containerapp up` | App Runner or ECS | App Platform or any Docker host |

The `cosmos`, `dynamodb` and `postgres` adapters are stubs. Selecting one fails with a clear message until someone implements the eight storage methods. Everything else in the table works as shown. Keep the rule: never call a cloud's login system from app code, and read secrets only from environment variables or mounted files.

The server is a standard FastAPI app in a Docker image, so it runs anywhere that runs containers.

- **Any container host** (Fly.io, Render, a VPS, Kubernetes): build the `Dockerfile` and run it. Set the same environment variables as in the table above.
- **AWS Lambda:** wrap the app with [Mangum](https://github.com/jordaniza/Mangum). Add this to a new `lambda_handler.py`:

  ```python
  from mangum import Mangum
  from app.main import app

  handler = Mangum(app)
  ```

  Deploy with a container image, or with a zip file that includes `app/` and the dependencies. Store the signing key in Secrets Manager and load it at startup.

- **Azure Functions:** use a container-based app, or the Python ASGI support. Store the signing key in Key Vault.

- **Cloudflare Workers:** the server is Python, and Workers run JavaScript. You'd port `app/main.py` to JavaScript, and reuse `verifiers/node/licensing.js` for signing checks. Treat this as a new implementation, and run `verifiers/cases.json` against it.

Things to change on any platform:
- The rate limit lives in memory, per instance. For a global limit, use the platform's gateway rate limiting (for example Cloud Armor, AWS WAF, or Cloudflare rate limiting).
- Scale-to-zero platforms restart the process often, so the signing key must load on each cold start from the secret store, not from a file in the image.

## Signing key for local builds

The Docker scripts never keep the signing key in the project folder. Each one reads the key from one of two places:

1. `LICENSE_SIGNING_KEY_FILE`: a PEM file outside the project, such as `~/.config/licensing/private.pem`. Use this if you have no cloud access.
2. `LICENSE_KEY_SOURCE`: `gcloud` (default), `aws` or `azure`. The script fetches the key into a temp file and deletes it when the script exits.

Set the variables in your shell before running the script. Don't put them in `.env`, because `.env` is copied into the image. `LICENSE_SECRET_NAME` defaults to `license-signing-key`.

### Create the secret (once per cloud account)

Run the command for your provider. It stores the key in the place the local build reads from. Replace `license-signing-key` if you use another name.

**Google Cloud (gcloud)**

```bash
gcloud secrets create license-signing-key --project YOUR_PROJECT --replication-policy=automatic
gcloud secrets versions add license-signing-key --project YOUR_PROJECT --data-file=private.pem
```

Fetch it locally: `export LICENSE_GCP_PROJECT=YOUR_PROJECT`, then run the script.

**AWS (Secrets Manager)**

```bash
aws secretsmanager create-secret --name license-signing-key --secret-string file://private.pem
```

Fetch it locally: `export LICENSE_KEY_SOURCE=aws`, then run the script. Your AWS credentials and region must be set in the shell.

**Azure (Key Vault)**

```bash
az keyvault secret set --vault-name YOUR_VAULT --name license-signing-key --file private.pem
```

Fetch it locally: `export LICENSE_KEY_SOURCE=azure LICENSE_AZURE_VAULT=YOUR_VAULT`, then run the script. You need the `az` CLI and `az login`.

**Cloudflare (Workers secret)**

```bash
npx wrangler secret put LICENSE_SIGNING_KEY < private.pem
```

Cloudflare secrets are write-only, so the scripts can't read them back. This stores the key for a Worker deploy only. For local builds, use one of the other options above.

**GitHub (Actions secret)**

```bash
gh secret set LICENSE_SIGNING_KEY < private.pem --repo YOUR_ORG/YOUR_REPO
```

GitHub secrets are also write-only. Use this for CI, and keep the local copy in one of the other stores above or in a local file.

**Local file (no cloud)**

```bash
mkdir -p ~/.config/licensing && cp private.pem ~/.config/licensing/private.pem && chmod 600 ~/.config/licensing/private.pem
export LICENSE_SIGNING_KEY_FILE=~/.config/licensing/private.pem
```

On Windows, use `%USERPROFILE%\.config\licensing\private.pem` and `set LICENSE_SIGNING_KEY_FILE=...` instead.

The root key (`keys/root_private.pem`) is not used by these scripts. It is only used offline by `sign_keylist.py`.

## Files needed to build

Put these in the same folder as the `Dockerfile`:

| File | What it is | Made by |
|---|---|---|
| `Dockerfile` | the build recipe | this repo |
| `keylist.json` | your signed key list | `sign_keylist.py` on your PC |
| `root-public.pem` | the root public key | `sign_keylist.py init-root` |
| `.env` | settings (copy `.env.example`) | you |
| `private.pem` | not in the folder. The Docker scripts read it from `LICENSE_SIGNING_KEY_FILE` or your cloud secret store, then mount it at run time. | `issue_license.py` setup |
| `gcp-sa.json` | Firestore service-account key (only if `.env` sets `GOOGLE_APPLICATION_CREDENTIALS`) | Google Cloud console |

The app code is fetched from the public GitHub repo during the build, so you don't need the `app/` folder.

Run `DockerBuild.bat` (Windows) or `./DockerBuild.sh` (Linux and Mac) from that folder. It checks for each file, stops with a clear message if one is missing, then builds and runs the server. Or build by hand with `docker build -t license-check .`.

## Settings in a .env file

Copy `.env.example` to `.env` in the repo root and fill it in. The server and every script read it, so you don't need to pass the storage flags each time. `.env` is gitignored. Real environment variables override it. Cloud Run ignores the file, so set the same variables on the service at deploy time.

## Deploy to Cloud Run

Run these from the folder that holds the `Dockerfile`, `keylist.json`, `root-public.pem` and `.env`. Cloud Build builds the image in Google Cloud. If `gcloud` reports "Building using Buildpacks", you are in the wrong folder.

**1. One-time setup** (replace the project ID if yours differs):
```
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com --project pigeonholes-license-server
PROJECT_NUMBER=$(gcloud projects describe pigeonholes-license-server --format="value(projectNumber)")
gcloud secrets add-iam-policy-binding license-signing-key --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" --role=roles/secretmanager.secretAccessor --project pigeonholes-license-server
gcloud projects add-iam-policy-binding pigeonholes-license-server --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" --role=roles/datastore.user
```
On Windows, replace `$(...)` with the number printed by `gcloud projects describe pigeonholes-license-server --format="value(projectNumber)"`.

**2. Deploy:**
```
gcloud run deploy license-check --source . --region europe-west1 --project pigeonholes-license-server --allow-unauthenticated --min-instances 0 --set-env-vars "LICENSE_STORAGE=firestore,LICENSE_FIRESTORE_PROJECT=pigeonholes-license-server,LICENSE_KID=k1,LICENSE_SIGNING_KEY_PATH=" --set-secrets LICENSE_SIGNING_KEY=license-signing-key:latest
```
Keep `LICENSE_SIGNING_KEY_PATH=` (empty). `.env` is copied into the image and sets `LICENSE_SIGNING_KEY_PATH=private.pem`, which doesn't exist on Cloud Run. The empty value overrides it, so the key comes from Secret Manager.

**3. Check it:** get the URL with `gcloud run services describe license-check --region europe-west1 --format="value(status.url)"`, then run the three checks in SKILL.md Step 1b.

Redeploy with the same command after each change. Run `gcloud run revisions list --service license-check --region europe-west1` to see past revisions.

## Deploy the server (other options)

Set the variables from the table below, then run this from the repo root. For Cloud Run:

```bash
gcloud run deploy license-check --source . --region REGION \
  --set-env-vars LICENSE_STORAGE=firestore,LICENSE_FIRESTORE_PROJECT=YOUR_PROJECT \
  --set-secrets LICENSE_SIGNING_KEY=license-signing-key:latest \
  --allow-unauthenticated --min-instances 0
```

Configuration (environment variables):

| Variable | Purpose |
|---|---|
| `LICENSE_STORAGE` | `json` (default, local testing) or `firestore` |
| `LICENSE_JSON_PATH` | JSON file path when storage is `json` |
| `LICENSE_FIRESTORE_PROJECT` | Google Cloud project ID when storage is `firestore` |
| `LICENSE_SIGNING_KEY_PATH` | Path to the Ed25519 private key PEM |
| `LICENSE_SIGNING_KEY` | Alternative: the PEM text itself |
| `LICENSE_VALID_DAYS` | How long a signed reply stays valid (default 7) |
| `LICENSE_KID` | The `kid` written into every signed reply (default `k1`) |
| `LICENSE_RATE_LIMIT_PER_MIN` | Checks per minute per client IP (default 60) |
| `LICENSE_KEYLIST_PATH` | Path to the signed key list served at `GET /v1/keys` (optional) |

Run locally:

```bash
pip install -r requirements.txt
LICENSE_STORAGE=json LICENSE_JSON_PATH=dev-data.json \
LICENSE_SIGNING_KEY_PATH=/path/to/private.pem \
uvicorn app.main:app --reload
```

## Test

Run the tests from the repo root:

- `pytest -q` runs the Python verifier and server tests.
- `node --test tests/node/test.js` runs the Node verifier tests.
- `cargo test` in `verifiers/rust/` runs the Rust tests.

The shared cases in `verifiers/cases.json` must pass in every verifier. The online replies in `verifiers/online-replies.json` (checked with `verifiers/online-public.pem`) cover the reply check. Python, Node, and Rust pass them. Dart is untested.

The repo includes