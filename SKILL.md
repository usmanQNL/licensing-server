---
name: add-licensing
description: Adds licensing to a project (license key, paywall, trial, subscription or feature gating) with signed license files, an optional daily online check and a grace period. Use when starting licensing for an app or service, adding a paywall or paid features, issuing license keys, or changing a project's license mode.
---

# Add licensing

Adds licensing to a project in a few steps. Ask the questions first, then set up the server, then make the changes, then test. Record every answer, choice, command and file in `licensing/licensing.md` in the target project as you go (see "The licensing record" below).

## The licensing record (`licensing/licensing.md`)

Every project this skill touches gets one file, `licensing/licensing.md`, that holds everything needed to run its licensing from start to finish. It is written for any agent or person, not for one tool: plain Markdown, no tool-specific steps, and every command written out in full so it can be copied and run.

**Before Step 1:** look for `licensing/licensing.md` in the target project.
- If it exists, read it first. Use its answers instead of asking again, and only ask about what is missing or what the user wants to change. Continue from the first step its "Progress" table does not show as done.
- If it does not exist, create it from the template at the end of this file as soon as the Step 1 answers are in.

**Keep it current.** Update it at the end of every step, not only at the end. Each step below says what to add. Record what was actually done (the real names, paths and commands that ran), not what the template suggests. When something changes later (a new feature, a key rotation, a new server URL), update the record in the same change.

**What it must never hold:** private keys, secret values, tokens, passwords or customer contact details (email, phone). For a private key, record only where it lives: the secret name and cloud project, or the file path outside the repo. For issued licenses, record only the license ID, plan, features and expiry.

**Older projects:** if the project has `licensing/features.md` from an earlier version of this skill, move its entries into the "Gated features" table of `licensing/licensing.md`, replace the old file's contents with a one-line pointer to `licensing/licensing.md`, and update the agent instruction files (Step 6) to point at `licensing/licensing.md`.

## Two keys, two jobs

Read this before Step 4. There are two Ed25519 keys, and they are not interchangeable.

- **Root key.** Signs the key list that apps use to trust signing keys. It is created once, stays offline, and never goes to the server or into git. Its public half, `root-public.pem`, ships inside the app as a constant.
- **Signing key.** Signs every license file and every server reply. It lives in Secret Manager (or a local PEM outside the repo) and is used by `issue_license.py` and the server. Only its public half goes into `keys.json`.

Apps trust the signing key because the root key vouches for it in `keylist.json`. Rotation adds a new signing key to the list without an app update.

## Step 1: ask these questions

Ask only what the chosen mode needs.

1. **Mode.** Pick one:
   - **OpenSource:** adds a free license file (question 2). No keys, no checks. Record the mode, the app name, the license and its files in `licensing/licensing.md`, then stop.
   - **Subscription:** a signed license with an expiry date, checked at launch, with a 14-day grace period. Its license must carry the `subscription` plan.
   - **Gated:** a signed license listing features. Each paid feature checks its flag before it runs. Its license must carry the `gated` plan. It can have an end date (`--expires-days` or `--expires-on`), with the same 14-day grace period; leave it out for a perpetual license.
2. **License.** Which license the project is published under. Every mode gets one, and the templates are in `templates/licenses/` (its `README.md` says where each file goes). If that folder is not next to this skill, use the copy at https://github.com/usmanQNL/licensing-server/tree/master/templates/licenses. Show the user the options for their mode with a one-line description each, and recommend the default.
   - **OpenSource** (pick one): **MIT** (default, the shortest and most used), **Apache-2.0** (adds a patent grant and a `NOTICE` file), **BSD-2-Clause**, or **BSD-3-Clause** (also bars using the owner's name to promote derived products). Then offer two optional add-ons:
     - **DCO sign-off:** contributors sign off each commit. Adds `DCO`, `CONTRIBUTING.md` and the `.github/workflows/dco.yml` check.
     - **Docs and assets license:** **CC-BY-4.0** (reuse with credit) or **CC0-1.0** (public domain) for a `docs/` or `assets/` folder. Never offer Creative Commons for code; Creative Commons says its licenses are not meant for software.
   - **Subscription or Gated** (pick one): **Proprietary EULA** (default: an "All rights reserved" `LICENSE` plus `EULA.md` whose seat, term, grace period and feature terms match the license file), **BUSL-1.1** (public source, production use is paid, each version turns into Apache-2.0 on a Change Date), **Elastic-2.0** (public source, no hosted-service resale, no bypassing license keys), or **PolyForm-Noncommercial-1.0.0** (free for noncommercial use, paid for commercial). If the user asks for dual licensing (for example AGPL plus a commercial license), follow the "Dual licensing" section of `templates/licenses/README.md`.
   - Ask for the **copyright holder** (person or company) and the **year**, plus anything the chosen template needs: for the EULA, the contact, pricing, refund policy and governing law; for BUSL-1.1, the Additional Use Grant and Change Date.
   - Copy the template, fill in only its `<...>` placeholders, and never change a standard license's wording. If the project already has a `LICENSE`, show it to the user and ask before replacing it.
   - Tell the user once, in plain words: this is not legal advice; the standard licenses are safe to use as they are, but the EULA template should be reviewed by a lawyer before they sell under it.
3. **Application name**, for example `QuellDAP`. Used in license folders, the license record, and the `.env` variable that holds the license file's location (`QUELLDAP_LICENSE_FILE`, see Step 6).
4. **Language**: Python, Node.js, Rust, or Dart/Flutter (untested).
5. **Licensing server.** Does the user already run one? If yes, get its endpoint URL and its root public key (or its key list URL), and skip Step 2. If no, deploy this repo's server in Step 2.
6. **Online check?** On by default. Users can turn it off. If on, the endpoint URL from question 5. That URL is also the **issuer URL**: it is signed into every license (`issuer_url`) and every server reply, so the app knows where to check and can't be pointed at another server. It must be `https` (`http` only for `localhost`).
7. **Gated features** (Gated mode only). List each paid feature. For each one get a **feature ID**, a short description and the code it will guard. The feature ID is the exact lowercase string that goes into the license's `features` list and into the verifier's feature check, for example `sso`, `hourly_sync`, `online_update`. It must never change once a license has been issued with it. Free features are not listed.
8. **Repositories and where things live.** The name (and URL, if any) of the app's repository, and of the licensing server's repository or deploy location if it has one. The cloud project (or other host) for the server, the license store and the signing secret, if those exist.

**Record:** write every question and its answer, word for word where it matters, into the "Answers" section of `licensing/licensing.md`. Fill the "Project license" table with the license, its SPDX ID, the copyright holder and year, the add-ons, and each file copied from `templates/licenses/`. For Gated, fill the "Gated features" table now. The guarded code can say "to be wrapped" until Step 6.

## Step 2: deploy the server (only if there is no server yet)

Follow `README.md`. It covers the storage backend (Firestore or any NoSQL database), the signing key in Secret Manager, the Cloud Run deploy and the environment variables. Manage licenses with `license_admin.py` (list, show, revoke, reinstate) or in the storage console. Any backend works with `--firestore-project` or `--json-path`.

Make the root key and the signing key (Step 4) before deploying, because the server needs the signing key and the key list.

Set `LICENSE_ISSUER_URL` on the server to its public URL, with no trailing slash. The server signs it into every reply as `issuer_url`, and `issue_license.py` reads the same variable as its default `--issuer-url`.

**Record:** the server repository or source folder, the host and region, the service name, the storage backend and its project or path, the environment variable names (not secret values), the deploy commands exactly as run, the resulting endpoint URL, and the `LICENSE_ISSUER_URL` value.

## Step 3: verify the server connection (required before going on)

Do this as soon as the server URL is known, either from the user or after deploying in Step 2. Do not go on to Step 4 until all three checks pass. Run each one and show the user the result. OpenSource projects skip this step.

Replace `SERVER` with the endpoint URL, with no trailing slash.

1. **Reachable.** Expect `{"ok": true}`:
   ```bash
   curl -sS https://SERVER/v1/health
   ```
2. **Key list (if the project uses one).** Expect HTTP 200 and JSON with `"kid": "root"`. The verifier checks the signature with the root public key:
   ```bash
   curl -sS -o keylist-from-server.json -w "%{http_code}\n" https://SERVER/v1/keys
   ```
   HTTP 503 means the server has no `LICENSE_KEYLIST_PATH` set yet. Fix that on the server, then retry.
3. **Signed check reply.** Send a test license ID that does not exist. Expect HTTP 200 and a reply with `"status": "unknown"`, a `signature`, and `"issuer_url"` equal to `SERVER` (if it's missing, set `LICENSE_ISSUER_URL` on the server). Verify it with the server's signing public key (`check_online_reply` or `checkOnlineReply`). Nothing is stored for an unknown license.
   ```bash
   curl -sS -X POST https://SERVER/v1/check \
     -H "Content-Type: application/json" \
     -d '{"license_id":"CONNECTION-TEST","install_hash":"connection-test-0001"}'
   ```

If a check fails, tell the user which one and why:
- Check 1 fails: the URL is wrong, the service is down, or it is not deployed.
- Check 2 returns 503: the key list is not configured on the server.
- Check 3 returns 413 or 429: the request was too large or rate limited. Wait a minute and retry.
- Check 3 returns a bad signature: the public key in the app is for a different server or key.

Only move on once all three pass. Add the endpoint to the app's settings, not as a hard-coded URL.

**Record:** the three commands with `SERVER` filled in, the date they passed, and the settings key or file where the app reads the endpoint.

## Step 4: keys

Skip the signing-key part if the user has an existing server and its public key. Skip everything in this step for OpenSource.

**a. Root key (once, offline).**
```bash
python sign_keylist.py init-root --out keys/root_private.pem
```
Keep `keys/root_private.pem` offline and out of git. Ship `root-public.pem` inside the app.

**b. Signing key (in Secret Manager, or a local PEM outside the repo).** Create it with your cloud tool or `openssl`, then store it. Never put the private key in the app or in git. Add the private-key patterns and `keys/` to `.gitignore`. The README "Signing key for local builds" section has the commands for each provider.

**c. Public half into `keys.json`** (no private key is copied):
```bash
gcloud secrets versions access latest --secret license-signing-key --project YOUR_PROJECT | python sign_keylist.py make-keys --kid k1 --key-stdin --out keys.json
```
Or use `--key-file PATH` if the key is a local file.

**d. Sign the key list with the root key:**
```bash
python sign_keylist.py sign --root-key-file keys/root_private.pem --keys keys.json --out keylist.json
```
Put `keylist.json` next to the Dockerfile (or upload it for the server) before issuing any license with the new kid.

Put only `root-public.pem` in the app. Never the root private key, and never the signing private key.

**Record:** for each key, its kid, its public key (the PEM text, which is safe to share), and where the private half lives (file path outside the repo, or secret name and cloud project). Also record where `root-public.pem`, `keys.json` and `keylist.json` are in the project and on the server, the key list URL, and every command from this step exactly as run.

## Step 5: issue license files

Use `issue_license.py` (in this repo). Run `python issue_license.py --help` for all options.

Each issue needs exactly one key source: `--key-secret NAME --project PROJECT` (reads Secret Manager at run time), or `--key-file PATH` for a local PEM. It also needs `--customer`, `--application`, `--plan`, and `--client-email`. `--client-phone` is optional. Contact details are stored in the license store only, never in the file.

Pass `--issuer-url SERVER` (or set `LICENSE_ISSUER_URL`) so the license carries the server's URL, signed. Use the same value as the server's `LICENSE_ISSUER_URL`. Leave it out only for licenses that never check online. Licenses issued without it stay valid and use the app's configured server URL.

Nothing in the file is encrypted. It is readable JSON with a signature, so the customer can see what it grants but cannot change it.

The license is a JSON file with `kid`, `payload` and `signature`. The application name is not in the file. The output goes to `licenses/<application>/<license_id>.license.json` by default, or to `--out PATH`.

**Delivering the file.** Send the `.license.json` file to the customer through your normal channel, and tell them where the app expects it: the path in `<APP_NAME>_LICENSE_FILE` in the app's `.env` (Step 6), or tell them to set that variable to wherever they put the file. Never commit `licenses/` or `*.license.json` to git.

**Record:** the `issue_license.py` command as a reusable template (with placeholders for the customer and contact details), the issuer URL used, the output folder, where the app expects the license file, and one row per issued license (license ID, plan, features, expiry). Never the customer's email or phone.

## Step 6: add the verifier

Copy the verifier for the chosen language into the project:
- Python: `verifiers/python/licensing.py`
- Node.js: `verifiers/node/licensing.js`
- Rust: `verifiers/rust/`
- Dart/Flutter: `verifiers/dart/licensing.dart` (untested. Run `dart test` against `verifiers/cases.json` first.)

### Where the app finds the license file (`.env`)

The license file's location lives in the project's `.env` file, in one variable named after the app:

- **Name:** `<APP_NAME>_LICENSE_FILE`. The application name from Step 1 in uppercase, with every run of other characters turned into `_`. `QuellDAP` gives `QUELLDAP_LICENSE_FILE`, `My App` gives `MY_APP_LICENSE_FILE`. A name that starts with a digit gets `APP_` in front.
- **Value:** the full path of the license file, with its file name and extension, for example `QUELLDAP_LICENSE_FILE=C:/apps/quelldap/license.json` or `QUELLDAP_LICENSE_FILE=/srv/quelldap/license.json`. Use forward slashes. A relative path still works and is resolved against the project root. If the user doesn't say where, use the full path of `license.json` in the project root.
- **Fallback:** when the variable is not set (not in the environment and not in `.env`), the app looks for `license.json` in the current working directory.

Do this in the target project:

1. If the project root has no `.env`, create it. Add the variable (or update it if it is already there). Don't touch other lines.
2. Make sure `.env` is in `.gitignore`. Also add `license.json` and `*.license.json` (or the license file's folder) so a license file is never committed.
3. Add the same line to `.env.example` (create it if missing), so anyone setting up the project sees the variable. `.env.example` is committed.
4. Load the license from that variable at startup. Every verifier has the lookup: `find_license_file(app_name, project_root)` in Python and Rust, `findLicenseFile(appName, projectRoot)` in Node, and `licenseFileEnvVar` with `parseDotenv` in Dart. It reads the variable from the real environment first, then from `<project root>/.env`. When neither has it, it returns `license.json` in the current working directory. A relative value resolves against the project root.
5. A missing or unreadable license file is not an error: paid features stay off, and the app still runs.

A real environment variable overrides `.env`, so an installed app or a server can point at a license somewhere else without editing the file.

### Where the app keeps what it fetches (`.env`: `<APP_NAME>_LICENSE_CACHE`)

The online check reply, `install_hash`, `install_token`, `last_seen` and the cached key list all live in one cache file (SPEC.md section 5a). Its location is the second variable in the same `.env`:

- **Name:** `<APP_NAME>_LICENSE_CACHE`, same naming rule (`QUELLDAP_LICENSE_CACHE`).
- **Value:** the cache file's full path, for example `QUELLDAP_LICENSE_CACHE=C:/apps/quelldap/license.cache.json`. A relative path resolves against the project root. Pick a folder the app can write to.
- **Fallback:** when unset, the file sits next to the license file, named after it (`license.json` gives `license.cache.json`).

Add the line to `.env` and `.env.example`, and add `*.cache.json` to `.gitignore`. Find it with `find_license_cache(app_name, project_root)` (Python, Rust) or `findLicenseCache(appName, projectRoot)` (Node). Dart has `licenseCacheEnvVar` and `defaultCacheFile`. The app creates the file on the first check, and a missing or damaged file is treated as empty.

Trust a key list (recommended) or one key. Use `load_trusted_keys` (Python) or `loadTrustedKeys` (Node) with the root public key, the server URL and the license cache path (it keeps the list in that file's `keylist` field). Rust and Dart take a fixed `{kid: PEM}` map. Each verifier:
1. Picks the key for the file's `kid` and verifies the signature. Rejects anything that fails.
2. Rejects unknown `v` values.
3. Checks the plan matches the chosen mode.
4. For Subscription: an expired license gets a 14-day grace period with a warning. After that, paid features turn off.
5. For Gated: checks the feature is in `features` before the feature runs. A gated license with `expires_at` expires like a subscription, with the same 14-day grace period.
6. Never blocks sign-in. A failed check only turns paid features off.

### Gated features: how to wrap them

For Gated mode, do this in the project:

1. Fill the "Gated features" table in `licensing/licensing.md`: one row per paid feature with its feature ID, what it does, the code it guards (file and function), and what the user sees when the license does not include it. There is no separate features file.
2. Add a short pointer to it in every agent instruction file the project has (for example `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, `.cursorrules`). If it has none, create `AGENTS.md` with it:

   > Licensing for this project is recorded in `licensing/licensing.md`. Paid features and their feature IDs are in its "Gated features" table. Before you edit code that uses one, wrap the code in the license check for that feature ID. Never gate a feature that is not listed. If you add a paid feature, add a row to that table and wrap it the same way.

3. Load the license once at startup, then wrap each paid feature with the verifier's feature check. Python:

   ```python
   import json
   from licensing import load_trusted_keys, evaluate, find_license_file, find_license_cache, refresh_online_status

   license_path = find_license_file("QuellDAP", project_root=APP_ROOT)  # QUELLDAP_LICENSE_FILE from .env
   license_text = open(license_path, encoding="utf-8").read()            # the customer's .license.json
   lic_id = json.loads(license_text)["payload"]["license_id"]
   cache_path = find_license_cache("QuellDAP", project_root=APP_ROOT)      # QUELLDAP_LICENSE_CACHE from .env
   keys = load_trusted_keys(ROOT_PUBLIC_PEM, cache_path=cache_path, endpoint=SERVER_URL)
   online = refresh_online_status(license_text, keys, cache_path, endpoint=SERVER_URL)  # Step 7; skip if off

   result = evaluate(license_text, keys, mode="gated", license_id=lic_id, features_needed=["online_update"],
                     reply_text=online.reply_text, last_seen=online.last_seen)
   if result.valid_for_paid_features:
       run_online_update()
   else:
       show_upgrade_message("online_update")
   ```

   Node uses `evaluate(...)` with `featuresNeeded: ['online_update']`. The full examples are in `verifiers/python/example_gated.py` and `verifiers/node/example_gated.js`.

Always test a valid license, an expired one, a tampered one, a wrong plan and a missing feature. Use the shared cases in `verifiers/cases.json`.

**Record:** the verifier's path in the project, the `<APP_NAME>_LICENSE_FILE` and `<APP_NAME>_LICENSE_CACHE` variable names and values, that `.env` and `*.cache.json` are gitignored and `.env.example` has both lines, where the app loads the license at startup, the root public key path, and for Gated the final guarded code for each feature ID.

## Step 7: online check (optional, on by default)

If on, the app calls `POST {server}/v1/check` once a day with `license_id` and `install_hash`. `{server}` is the license's signed `issuer_url`; a license without one uses the app's configured server URL. `install_hash` is a random ID the app creates once. It holds no personal data.

How it works, so you can explain it to the user:
- **Fetch:** the app sends the request. The server looks up the license and seats and replies with a signed status (`active`, `revoked`, `unknown` or `limit_reached`), `checked_at`, `valid_until` (7 days by default) and `issuer_url`. The first reply for a new install also carries an `install_token`, once. Every later check must send it, or the server returns HTTP 403.
- **Signed, not encrypted:** the reply is readable JSON. The app verifies its Ed25519 signature with the same public key as the license (matched by `kid`), checks `license_id`, checks `issuer_url` matches the license's, and checks `valid_until`. Nothing is decrypted.
- **Cache:** the last valid reply, `install_hash`, `install_token` and `last_seen` are kept in the license cache file (`<APP_NAME>_LICENSE_CACHE`, Step 6).
- **Offline:** when the server can't be reached, the cached reply is used until its `valid_until`, then the license alone decides (with its 14-day grace period). An app with no network at all runs on the license until it expires. A revoke only takes effect at the next successful check.

Use the helper, which does all of the above: `refresh_online_status(license_text, keys, cache_path, endpoint=SERVER_URL)` in Python, `await refreshOnlineStatus(licenseText, keys, { cachePath, endpoint })` in Node. It checks at most once a day, never throws for network errors, and returns the reply and `last_seen` to pass to `evaluate`. Rust and Dart have no network helper: send the request yourself, keep the same cache file (SPEC.md section 5a), and check replies with `check_online_reply_for_issuer` (Rust) so the issuer match applies.

- `revoked`, `unknown` and `limit_reached` turn paid features off at the next successful check. Sign-in is never blocked.
- Let users turn this off in settings. Never hard-code the endpoint URL.

**Record:** on or off, the issuer URL in the licenses, the fallback endpoint setting, the settings key that turns it off, the cache file path (`<APP_NAME>_LICENSE_CACHE`), and the check interval.

## Step 8: test

- Python: `pytest -q`
- Node: `node --test tests/node/test.js`
- Rust: `cargo test` in `verifiers/rust/`
- Dart: `dart test` (untested)

The shared cases in `verifiers/cases.json` and the online replies in `verifiers/online-replies.json` must pass before the project ships.

**Record:** the exact test commands for this project, the date they last passed, and mark every step done in the "Progress" table. The work is not finished until `licensing/licensing.md` is complete.

## Rules

- Keep the private keys (root and signing) out of git and out of app code.
- Licensing is a deterrent, not DRM. A check on the user's machine can always be bypassed. Say so in the project docs.
- Use only the mode the user chose. Don't add checks they didn't ask for.
- Copy license texts from `templates/licenses/` word for word and fill only the placeholders. Creative Commons is for docs and assets, never code. Say once that this is not legal advice, and that the EULA template needs a lawyer's review.
- App stores may require in-app purchase for paid digital features on iOS and Android. Check before adding licensing to a mobile app.
- The license file's location goes in `.env` as `<APP_NAME>_LICENSE_FILE`, and the cache file's as `<APP_NAME>_LICENSE_CACHE`, never hard-coded. Keep `.env`, license files and cache files out of git.
- Keep `licensing/licensing.md` current. It is the single source of truth for this project's licensing, and the next agent starts from it.

## Template: `licensing/licensing.md`

Copy this into the target project and fill it in. Leave out sections the chosen mode does not use (OpenSource needs only the header, "Answers", "Project license" and "Files and folders"). Replace every `<...>`; write "n/a" rather than leaving a placeholder.

````markdown
# Licensing record: <application name>

This file records how licensing is set up for this project, so that any agent or person can run, change or repeat it without asking again. It was created with the add-licensing skill (https://github.com/usmanQNL/licensing-server). It holds no private keys or secrets, only where they live.

Last updated: <YYYY-MM-DD>

## Progress

| Step | Status | Date | Notes |
|---|---|---|---|
| 1. Questions answered | done / todo | | |
| 2. Server deployed | done / skipped (existing server) / todo | | |
| 3. Server connection verified | done / todo | | |
| 4. Keys created and key list signed | done / skipped / todo | | |
| 5. First license issued | done / todo | | |
| 6. Verifier added (and features wrapped) | done / todo | | |
| 7. Online check | done / off / todo | | |
| 8. Tests passing | done / todo | | |

## Answers

| Question | Answer |
|---|---|
| Mode | <OpenSource / Subscription / Gated> |
| License | <MIT / Apache-2.0 / BSD-2-Clause / BSD-3-Clause / Proprietary EULA / BUSL-1.1 / Elastic-2.0 / PolyForm-Noncommercial-1.0.0 / dual> |
| License plan in the file | <subscription / gated> |
| Application name | <QuellDAP> |
| Language | <Python / Node.js / Rust / Dart> |
| Existing licensing server? | <yes: URL / no: deployed in Step 2> |
| Server endpoint URL | <https://...> |
| Key list URL | <https://.../v1/keys> |
| Online check | <on / off> |
| Grace period | <14 days> |
| Other answers or decisions | <anything else the user said that changes the setup> |

## Project license

Not legal advice. Standard licenses are copied word for word from `templates/licenses/`; only placeholders were filled.

| Item | Value |
|---|---|
| License | <MIT License> |
| SPDX ID | <MIT / Apache-2.0 / BSD-2-Clause / BSD-3-Clause / LicenseRef-Proprietary / BUSL-1.1 / Elastic-2.0 / PolyForm-Noncommercial-1.0.0> |
| Copyright holder and year | <Name, 2026> |
| DCO sign-off | <yes: DCO, CONTRIBUTING.md, .github/workflows/dco.yml / no> |
| Docs and assets license | <CC-BY-4.0 for docs/ / CC0-1.0 for assets/ / none> |
| Template parameters | <BUSL-1.1: Additional Use Grant, Change Date / EULA: governing law, refund policy / n/a> |
| Lawyer review of the EULA | <done on YYYY-MM-DD / not yet / n/a> |

| File in the project | Copied from |
|---|---|
| `LICENSE` | <templates/licenses/open-source/MIT.txt> |
| <NOTICE / EULA.md / DCO / CONTRIBUTING.md / docs/LICENSE> | <template path> |

## Repositories and hosting

| What | Name / location |
|---|---|
| App repository | <owner/repo or local path> |
| Licensing server repository or source | <owner/repo or path> |
| Server host, region, service name | <e.g. Cloud Run, us-central1, license-server> |
| Cloud project | <project id> |
| License store | <Firestore in project X / JSON at path> |

## Keys

| Key | kid | Public key | Where the private key lives |
|---|---|---|---|
| Root | root | `root-public.pem` (contents below) | <path outside the repo, kept offline> |
| Signing | <k1> | in `keys.json` (contents below) | <secret name in project X, or file path> |

```
<root-public.pem contents>
```

Key list files: `keys.json` at <path>, `keylist.json` at <path> (and on the server at <path or env var>).

## Files and folders created or changed

| Path | Purpose |
|---|---|
| `licensing/licensing.md` | this record |
| `LICENSE` (and any other license files) | the project license, see "Project license" |
| <path to verifier> | license verifier |
| <path to root-public.pem> | trusted root public key shipped in the app |
| <app settings file / key> | server endpoint and online-check setting |
| `.env` | `<APP_NAME>_LICENSE_FILE=<full/path/license.json>` and `<APP_NAME>_LICENSE_CACHE=<full/path/license.cache.json>` (gitignored, created if missing) |
| `.env.example` | the same variable, committed, so setup shows it |
| `.gitignore` | ignores `.env`, `license.json`, `*.license.json`, `*.cache.json`, `keys/`, `licenses/`, private key patterns |
| <AGENTS.md / other agent files> | pointer to this record |
| <...> | <...> |

## Commands

Every command used, in the order they were run, with real names and paths. Placeholders only for per-customer values.

```bash
# Step 2: deploy
<command>

# Step 3: verify the server
curl -sS <SERVER>/v1/health
curl -sS -o keylist-from-server.json -w "%{http_code}\n" <SERVER>/v1/keys
curl -sS -X POST <SERVER>/v1/check -H "Content-Type: application/json" -d '{"license_id":"CONNECTION-TEST","install_hash":"connection-test-0001"}'

# Step 4: keys
<command>

# Step 5: issue a license (template)
python issue_license.py <key source> --customer "<CUSTOMER>" --application <app> --plan <plan> --client-email "<EMAIL>" --issuer-url <SERVER> <other options as used>

# Manage licenses
python license_admin.py <list / show / revoke / reinstate> <...>
```

## Verifier and app wiring

| Item | Value |
|---|---|
| Verifier path | <path> |
| Where the license is loaded at startup | <file:function> |
| License file variable (in `.env`) | <QUELLDAP_LICENSE_FILE> |
| License file location (its value, a full path) | <C:/apps/quelldap/license.json> |
| License cache variable (in `.env`) | <QUELLDAP_LICENSE_CACHE> |
| License cache location (its value, a full path) | <C:/apps/quelldap/license.cache.json> |

## Online check

| Item | Value |
|---|---|
| Enabled | <yes / no> |
| Issuer URL (signed into licenses and replies) | <SERVER> |
| Fallback endpoint setting (licenses without issuer_url) | <settings key> |
| Interval | <once a day> |
| Setting that turns it off | <settings key> |
| Cache file (install_hash, install_token, cached reply, last_seen, key list) | <path from QUELLDAP_LICENSE_CACHE> |

## Gated features

Feature IDs are the exact strings in the license's `features` list. Never rename one that has been issued.

| Feature ID | Description | Guarded code | When not licensed |
|---|---|---|---|
| <online_update> | <what it does> | <file:function> | <upgrade message / hidden> |

## Issued licenses

No customer contact details here; those stay in the license store.

| License ID | Plan | Features | Expires | Issued |
|---|---|---|---|---|
| <id> | <plan> | <features> | <date> | <date> |

## Tests

| Command | Last passed |
|---|---|
| <pytest -q> | <date> |

## Notes

<Anything else the next agent needs: open issues, decisions, what to do next.>
````
