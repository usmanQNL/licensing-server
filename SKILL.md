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
   - **OpenSource:** adds an MIT `LICENSE` file. No keys, no checks. Record the mode, the app name and the `LICENSE` file in `licensing/licensing.md`, then stop.
   - **Subscription:** a signed license with an expiry date, checked at launch, with a 14-day grace period. Its license must carry the `subscription` plan.
   - **Gated:** a signed license listing features. Each paid feature checks its flag before it runs. Its license must carry the `gated` plan. It can have an end date (`--expires-days` or `--expires-on`), with the same 14-day grace period; leave it out for a perpetual license.
2. **Application name**, for example `QuellDAP`. Used in license folders and the license record.
3. **Language**: Python, Node.js, Rust, or Dart/Flutter (untested).
4. **Licensing server.** Does the user already run one? If yes, get its endpoint URL and its root public key (or its key list URL), and skip Step 2. If no, deploy this repo's server in Step 2.
5. **Online check?** On by default. Users can turn it off. If on, the endpoint URL from question 4.
6. **Gated features** (Gated mode only). List each paid feature. For each one get a **feature ID**, a short description and the code it will guard. The feature ID is the exact lowercase string that goes into the license's `features` list and into the verifier's feature check, for example `sso`, `hourly_sync`, `online_update`. It must never change once a license has been issued with it. Free features are not listed.
7. **Repositories and where things live.** The name (and URL, if any) of the app's repository, and of the licensing server's repository or deploy location if it has one. The cloud project (or other host) for the server, the license store and the signing secret, if those exist.

**Record:** write every question and its answer, word for word where it matters, into the "Answers" section of `licensing/licensing.md`. For Gated, fill the "Gated features" table now. The guarded code can say "to be wrapped" until Step 6.

## Step 2: deploy the server (only if there is no server yet)

Follow `README.md`. It covers the storage backend (Firestore or any NoSQL database), the signing key in Secret Manager, the Cloud Run deploy and the environment variables. Manage licenses with `license_admin.py` (list, show, revoke, reinstate) or in the storage console. Any backend works with `--firestore-project` or `--json-path`.

Make the root key and the signing key (Step 4) before deploying, because the server needs the signing key and the key list.

**Record:** the server repository or source folder, the host and region, the service name, the storage backend and its project or path, the environment variable names (not secret values), the deploy commands exactly as run, and the resulting endpoint URL.

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
3. **Signed check reply.** Send a test license ID that does not exist. Expect HTTP 200 and a reply with `"status": "unknown"` and a `signature`. Verify it with the server's signing public key (`check_online_reply` or `checkOnlineReply`). Nothing is stored for an unknown license.
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

The license is a JSON file with `kid`, `payload` and `signature`. The application name is not in the file. The output goes to `licenses/<application>/<license_id>.license.json` by default, or to `--out PATH`.

**Delivering the file.** Send the `.license.json` file to the customer through your normal channel, and tell them where the app expects it. Never commit `licenses/` to git.

**Record:** the `issue_license.py` command as a reusable template (with placeholders for the customer and contact details), the output folder, where the app expects the license file, and one row per issued license (license ID, plan, features, expiry). Never the customer's email or phone.

## Step 6: add the verifier

Copy the verifier for the chosen language into the project:
- Python: `verifiers/python/licensing.py`
- Node.js: `verifiers/node/licensing.js`
- Rust: `verifiers/rust/`
- Dart/Flutter: `verifiers/dart/licensing.dart` (untested. Run `dart test` against `verifiers/cases.json` first.)

Trust a key list (recommended) or one key. Use `load_trusted_keys` (Python) or `loadTrustedKeys` (Node) with the root public key, the server URL and a cache path. Rust and Dart take a fixed `{kid: PEM}` map. Each verifier:
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
   from licensing import load_trusted_keys, evaluate

   license_text = open(LICENSE_PATH, encoding="utf-8").read()          # the customer's .license.json
   lic_id = json.loads(license_text)["payload"]["license_id"]
   keys = load_trusted_keys(ROOT_PUBLIC_PEM, cache_path=CACHE_PATH, endpoint=SERVER_URL)

   result = evaluate(license_text, keys, mode="gated", license_id=lic_id, features_needed=["online_update"])
   if result.valid_for_paid_features:
       run_online_update()
   else:
       show_upgrade_message("online_update")
   ```

   Node uses `evaluate(...)` with `featuresNeeded: ['online_update']`. The full examples are in `verifiers/python/example_gated.py` and `verifiers/node/example_gated.js`.

Always test a valid license, an expired one, a tampered one, a wrong plan and a missing feature. Use the shared cases in `verifiers/cases.json`.

**Record:** the verifier's path in the project, where the app loads the license at startup, the root public key path, the key list cache path, and for Gated the final guarded code for each feature ID.

## Step 7: online check (optional, on by default)

If on, the app calls `POST {endpoint}/v1/check` once a day with `license_id` and `install_hash`. `install_hash` is a random ID the app creates once and stores locally. It holds no personal data.

- The first reply includes an `install_token`. Store it and send it on every later check. Without it, the server returns HTTP 403.
- Check the reply with `check_online_reply` (Python) or `checkOnlineReply` (Node). Combine it with the license using `evaluate`. Pass `last_seen` (the newest time the app has seen) so setting the clock back can't extend anything.
- Cache the last valid reply and reuse it while the server is unreachable, until its `valid_until`.
- `revoked`, `unknown` and `limit_reached` turn paid features off at the next successful check. Sign-in is never blocked.
- Let users turn this off in settings. Never hard-code the endpoint URL.

**Record:** on or off, the endpoint, the settings key that turns it off, where `install_hash`, `install_token` and the cached reply are stored, and the check interval.

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
- App stores may require in-app purchase for paid digital features on iOS and Android. Check before adding licensing to a mobile app.
- Keep `licensing/licensing.md` current. It is the single source of truth for this project's licensing, and the next agent starts from it.

## Template: `licensing/licensing.md`

Copy this into the target project and fill it in. Leave out sections the chosen mode does not use (OpenSource needs only the header, "Answers" and "Files and folders"). Replace every `<...>`; write "n/a" rather than leaving a placeholder.

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
| License plan in the file | <subscription / gated> |
| Application name | <QuellDAP> |
| Language | <Python / Node.js / Rust / Dart> |
| Existing licensing server? | <yes: URL / no: deployed in Step 2> |
| Server endpoint URL | <https://...> |
| Key list URL | <https://.../v1/keys> |
| Online check | <on / off> |
| Grace period | <14 days> |
| Other answers or decisions | <anything else the user said that changes the setup> |

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
| <path to verifier> | license verifier |
| <path to root-public.pem> | trusted root public key shipped in the app |
| <app settings file / key> | server endpoint and online-check setting |
| `.gitignore` | ignores `keys/`, `licenses/`, private key patterns |
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
python issue_license.py <key source> --customer "<CUSTOMER>" --application <app> --plan <plan> --client-email "<EMAIL>" <other options as used>

# Manage licenses
python license_admin.py <list / show / revoke / reinstate> <...>
```

## Verifier and app wiring

| Item | Value |
|---|---|
| Verifier path | <path> |
| Where the license is loaded at startup | <file:function> |
| Where the app expects the license file | <path on the user's machine> |
| Key list cache path | <path> |

## Online check

| Item | Value |
|---|---|
| Enabled | <yes / no> |
| Endpoint | <SERVER>/v1/check |
| Interval | <once a day> |
| Setting that turns it off | <settings key> |
| Where install_hash, install_token and the cached reply are stored | <path> |

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
