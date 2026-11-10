---
name: add-licensing
description: Adds licensing to a project in one of four modes (OpenSource, Subscription, Gated, Full) with signed license files, an optional daily online check and a grace period. Use when starting licensing for an app or service, or changing a project's license mode.
---

# Add licensing

Adds licensing to a project in a few steps. Ask the questions first, then make the changes, then test.

## Step 1: ask these questions

Ask only what the chosen mode needs.

0. **Does the user already run a licensing server?** If yes, ask for its endpoint URL and its signing public key(s), or its key list URL. Skip Step 6. If no, this repo's server can be deployed (Step 6).
1. **Mode.** Pick one:
   - **OpenSource:** adds an MIT `LICENSE` file. No keys, no checks. Stop here.
   - **Subscription:** a signed license with an expiry date, checked at startup.
   - **Gated:** a signed license listing features. Each paid feature checks its flag before it runs.
   - **Full:** a signed license with an expiry date, checked at launch, with a 14-day grace period.
2. **Application name**, for example `QuellDAP`. Used in license folders and the license record.
3. **Language**: Python, Node.js, Rust, or Dart/Flutter (untested).
4. **Online check?** On by default. Users can turn it off. If on, the endpoint URL (from question 0, or a new server).
5. **Gated features** (Gated mode only). List each paid feature by name, for example `sso`, `hourly_sync`, `online_update`. Free features are not listed.

## Step 1b: verify the server connection (required before anything else)

Do this as soon as the server URL is known, either from the user or after deploying in Step 6. Do not go on to Step 2 until all three checks pass. Run each one and show the user the result.

Replace `SERVER` with the endpoint URL, with no trailing slash.

1. **Reachable.** Expect `{"ok": true}`:
   ```bash
   curl -sS https://SERVER/v1/health
   ```
2. **Key list (if the project uses one).** Expect HTTP 200 and JSON with `"kid": "root"`. The verifier checks the signature with the root public key:
   ```bash
   curl -sS -o keylist.json -w "%{http_code}\n" https://SERVER/v1/keys
   ```
   HTTP 503 means the server has no `LICENSE_KEYLIST_PATH` set yet. Fix that on the server, then retry.
3. **Signed check reply.** Send a test license ID that does not exist. Expect HTTP 200 and a reply with `"status": "unknown"` and a `signature`. Verify it with the server's signing public key (`check_online_reply` or `checkOnlineReply`). Nothing is stored for an unknown license.
   ```bash
   curl -sS -X POST https://SERVER/v1/check \
     -H "Content-Type: application/json" \
     -d '{"license_id":"CONNECTION-TEST","install_hash":"connection-test-0001"}'
   ```

If a check fails, tell the user which one and why:
- Step 1 fails: the URL is wrong, the service is down, or it is not deployed.
- Step 2 returns 503: the key list is not configured on the server.
- Step 3 returns 413 or 429: the request was too large or rate limited. Wait a minute and retry.
- Step 3 returns a bad signature: the public key in the app is for a different server or key.

Only move on once all three pass. Add the endpoint to the app's settings, not as a hard-coded URL.

## Step 2: keys

Skip this step if the user has an existing server and a public key from it.

- Generate one Ed25519 key pair for the product. Keep the private key in Google Secret Manager, or in a local PEM outside the repo.
- Add `*.pem`, `*.key` and `licenses/` to `.gitignore`.
- Put only the public key in the app, as a constant. Never the private key.

## Step 3: issue license files

Use `issue_license.py` (in this repo). Run `python issue_license.py --help` for all options. The license is a JSON file with `kid`, `payload` and `signature`. The application name is not in the file, only in the output folder and the license record.

Each issue needs `--client-email`, and `--client-phone` is optional. Those contact details are stored in the license store only, never in the file.

## Step 4: add the verifier

Copy the verifier for the chosen language into the project:
- Python: `verifiers/python/licensing.py`
- Node.js: `verifiers/node/licensing.js`
- Rust: `verifiers/rust/`
- Dart/Flutter: `verifiers/dart/licensing.dart` (untested. Run `dart test` against `verifiers/cases.json` first.)

Trust a key list (recommended) or one key. Use `load_trusted_keys` (Python) or `loadTrustedKeys` (Node) with the root public key, the server URL and a cache path. Rust and Dart take a fixed `{kid: PEM}` map. Each verifier:
1. Picks the key for the file's `kid` and verifies the signature. Rejects anything that fails.
2. Rejects unknown `v` values.
3. Checks the plan matches the chosen mode.
4. For Subscription and Full: an expired license gets a 14-day grace period with a warning. After that, paid features turn off.
5. For Gated: checks the feature is in `features` before the feature runs.
6. Never blocks sign-in. A failed check only turns paid features off.

### Gated features: how to wrap them

For Gated mode, do this in the project:

1. Create `licensing/features.md` with one line per paid feature: its name, what it does, and the code it guards.
2. Add a short pointer to it in `CLAUDE.md`, `AGENTS.md` and `GEMINI.md` (whichever the project uses):

   > Paid features are listed in `licensing/features.md`. Before you edit code that uses one, wrap the code in the license check for that feature. Never gate a feature that is not listed. If you add a paid feature, add it to that file and wrap it the same way.

3. Wrap each paid feature with the verifier's feature check. Python:

   ```python
   result = evaluate(license_text, keys, mode="gated", license_id=lic_id, features_needed=["online_update"])
   if result.valid_for_paid_features:
       run_online_update()
   else:
       show_upgrade_message("online_update")
   ```

   Node uses `evaluate(...)` with `featuresNeeded: ['online_update']`. The examples are in `verifiers/python/example_gated.py` and `verifiers/node/example_gated.js`.

Always test a valid license, an expired one, a tampered one, a wrong plan and a missing feature. Use the shared cases in `verifiers/cases.json`.

## Step 5: online check (optional, on by default)

If on, the app calls `POST {endpoint}/v1/check` once a day with `license_id` and `install_hash`. `install_hash` is a random ID the app creates once and stores locally. It holds no personal data.

- The first reply includes an `install_token`. Store it and send it on every later check. Without it, the server returns HTTP 403.
- Check the reply with `check_online_reply` (Python) or `checkOnlineReply` (Node). Combine it with the license using `evaluate`. Pass `last_seen` (the newest time the app has seen) so setting the clock back can't extend anything.
- Cache the last valid reply and reuse it while the server is unreachable, until its `valid_until`.
- `revoked`, `unknown` and `limit_reached` turn paid features off at the next successful check. Sign-in is never blocked.
- Let users turn this off in settings. Never hard-code the endpoint URL.

## Step 6: deploy the server (only if there is no server yet)

Follow `README.md`. It covers the storage backend (Firestore or any NoSQL database), the Secret Manager key, the Cloud Run deploy and the environment variables. Manage licenses with `license_admin.py` (list, show, revoke, reinstate) or in the storage console. Any backend works with `--firestore-project` or `--json-path`.

## Step 7: test

- Python: `pytest -q`
- Node: `node --test tests/node/test.js`
- Rust: `cargo test` in `verifiers/rust/`
- Dart: `dart test` (untested)

The shared cases in `verifiers/cases.json` and the online replies in `verifiers/online-replies.json` must pass before the project ships.

## Rules

- Keep the private key out of git and out of app code.
- Licensing is a deterrent, not DRM. A check on the user's machine can always be bypassed. Say so in the project docs.
- Use only the mode the user chose. Don't add checks they didn't ask for.
- App stores may require in-app purchase for paid digital features on iOS and Android. Check before adding licensing to a mobile app.
