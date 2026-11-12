# Plan and gate samples

Two checks, in six languages. Each sample reuses the verifier in `verifiers/` where one exists.

- **Licensing Plan** prints the installed license plan as JSON.
- **Licensing Gate** answers `true` or `false` for one feature.

| Language | Plan | Gate | Built on |
|---|---|---|---|
| Python | [`python/plan.py`](python/plan.py) | [`python/gate.py`](python/gate.py) | `verifiers/python/licensing.py` |
| Rust | [`rust/src/bin/plan.rs`](rust/src/bin/plan.rs) | [`rust/src/bin/gate.rs`](rust/src/bin/gate.rs) | `verifiers/rust` (path dependency) |
| Ruby | [`ruby/plan.rb`](ruby/plan.rb) | [`ruby/gate.rb`](ruby/gate.rb) | [`ruby/license_checks.rb`](ruby/license_checks.rb), a small verifier (no Ruby verifier existed) |
| Vanilla JS | [`vanilla-js/license-checks.js`](vanilla-js/license-checks.js) `licensePlan()` | same file, `isFeatureEnabled()` | Web Crypto port of `verifiers/node/licensing.js` |
| React | [`react/LicenseChecks.jsx`](react/LicenseChecks.jsx) `<LicensePlan>` | `<FeatureGate>` and `useFeature()` | `vanilla-js/license-checks.js` |
| curl | [`curl/plan.sh`](curl/plan.sh) | [`curl/gate.sh`](curl/gate.sh) | `jq` and `openssl`, plus `curl` for `/v1/check` |

For a Node.js server, use `verifiers/node/licensing.js` directly, or `vanilla-js/license-checks.js`, which also runs on Node 20+.

## Server-side gate (the one that can't be bypassed)

A check in the browser, or in an app the user can patch, only hides things. To really protect a paid feature, put the check on a server: the server holds the license, and a gated route answers HTTP 403 when the license doesn't include its feature. Each server also serves `GET /license/plan`, so the frontend shows or hides UI from the server's answer.

| Language | Server gate | How a route is gated |
|---|---|---|
| Python (FastAPI) | [`python/server_fastapi.py`](python/server_fastapi.py) | `dependencies=[Depends(require_feature("export_pdf"))]` |
| Node (Express), backend for React and vanilla JS | [`node/server_express.js`](node/server_express.js) | `app.get('/reports/pdf', requireFeature('export_pdf'), handler)` |
| Ruby (Rack: Rails, Sinatra) | [`ruby/license_gate_middleware.rb`](ruby/license_gate_middleware.rb), example [`ruby/config.ru`](ruby/config.ru) | `use LicenseGateMiddleware, gates: { '/reports/pdf' => 'export_pdf' }, ...` |
| Rust (axum) | [`rust/server/src/main.rs`](rust/server/src/main.rs) | `require_feature("export_pdf", cfg, routes)` |
| React | `<ServerLicenseProvider>` in [`react/LicenseChecks.jsx`](react/LicenseChecks.jsx) | reads `/license/plan`; `<FeatureGate>` works as before |
| curl | [`curl/call-server.sh`](curl/call-server.sh) | calls `/license/plan` and a gated route, shows the HTTP status |

```bash
cd samples/python && uvicorn server_fastapi:app --port 8000
cd samples/node && npm install && npm start
cd samples/ruby && gem install rack rackup webrick && rackup -p 8000
cd samples/rust/server && cargo run

bash samples/curl/call-server.sh http://localhost:8000 /reports/pdf    # HTTP 403 with the demo gated license
bash samples/curl/call-server.sh http://localhost:8000 /auth/sso       # HTTP 200
```

Every server finds the license through `APP_NAME` (default `Demo`) and `<APP_NAME>_LICENSE_FILE`, read from the environment or from `.env` in the folder you start it in. The value is the license's full path, for example `APP_NAME=QuellDAP` with `QUELLDAP_LICENSE_FILE=/srv/quelldap/license.json` in `.env`. When it is unset, the server uses `license.json` in the folder you start it in, and the demo license if there is none. It reads `LICENSE_PUBLIC_KEY` and `LICENSE_FEATURES` from the environment, and uses the demo files for anything unset. It re-reads and re-verifies the license on each gated request, so a renewed license file or an expiry takes effect without a restart. A missing or broken license file means every gated route answers 403. A refused request gets:

```json
{ "error": "feature_not_licensed", "feature": "export_pdf", "reason": "the license does not include this feature" }
```

The samples check the license file offline only. Licenses can also carry a signed `issuer_url` (the licensing server's URL), and the samples ignore it. To add the daily online check, call the verifier's `refresh_online_status` (Python) or `refreshOnlineStatus` (Node) at startup and pass its reply to `evaluate`. It keeps everything it fetches in the cache file named by `<APP_NAME>_LICENSE_CACHE` in the same `.env`, or next to the license file when that is unset (README, "Where the app keeps what it fetches").

These servers check one installed license, which fits a self-hosted app (each customer runs your server with their license). For a multi-tenant SaaS, store each customer's license with their account and load that one in the gate instead of a single file.

In a vanilla JS page, call the server the same way: `const plan = await (await fetch('/license/plan')).json();`, then hide what `plan.features` marks as disabled.

## Try them with the demo files

`demo/` has a public key, three signed demo licenses (gated, subscription, expired) and a feature list. The private key that signed them was thrown away. Every sample uses these files when you pass no arguments.

```bash
python samples/python/plan.py                      # plan JSON
python samples/python/gate.py sso                  # true
python samples/python/gate.py export_pdf           # false (not in the gated license)

ruby samples/ruby/plan.rb
ruby samples/ruby/gate.rb sso
ruby samples/ruby/test_cases.rb                    # runs verifiers/cases.json

cd samples/rust && cargo run --bin plan && cargo run --bin gate -- sso

bash samples/curl/plan.sh
bash samples/curl/gate.sh sso

cd samples && python -m http.server 8000           # then open http://localhost:8000/vanilla-js/
```

With your own files: `plan <license.json> <license-public.pem> <features.json>` and `gate <feature> <license.json> <license-public.pem>`. Gate scripts exit with 0 for `true` and 1 for `false`.

## Plan output

```json
{
  "valid": true,
  "status": "active",
  "reason": "valid",
  "license_id": "LIC-DEMO-GATED",
  "customer": "Demo Customer",
  "name": "gated",
  "start": "2026-11-01T00:00:00Z",
  "expires": "2036-11-01T00:00:00Z",
  "perpetual": false,
  "max_installs": 2,
  "features": [
    { "name": "sso", "enabled": true },
    { "name": "hourly_sync", "enabled": true },
    { "name": "online_update", "enabled": false },
    { "name": "export_pdf", "enabled": false }
  ]
}
```

- `status` is `active`, `grace` (expired, but within the 14-day grace period), `expired`, or `invalid`.
- `name` is the plan (`opensource`, `subscription`, `gated`). Legacy `full` licenses show as `subscription`.
- `start` is `issued_at` and `expires` is `expires_at` from the license. `expires` is null for a perpetual license.
- If the signature fails, every license field is null and every feature is disabled. Fields from a file that fails its signature are never shown.
- Rust prints the same keys in alphabetical order.
- The curl sample adds `server_status` (see below).

The license only lists the features that are on. To list the disabled ones too, pass the app's full feature list (the table in `licensing/licensing.md`) as `features.json`, a plain JSON array. Licensed features that are missing from that list are still shown.

## Gate rule

A feature is enabled when both of these are true:

1. The license verifies: signature, `v`, and expiry with grace (SPEC.md section 3).
2. The plan is `subscription` (all paid features on), or the feature is in the license's `features` list.

The plan and the gate use the same rule, so they never disagree.

## Limits

- **Browser (vanilla JS and React):** anyone can edit code in devtools. Use these checks to show or hide UI. Check anything that matters (downloads, paid API calls) on your server, with the server-side gate above. Ed25519 in Web Crypto needs Chrome or Edge 137+, Firefox 129+, or Safari 17+.
- **curl:** curl can't check a signature, so `plan.sh` verifies the license with `openssl` (3.0+) and `jq`. curl is used only for the optional live status. Set `LICENSE_SERVER`, `INSTALL_HASH` and `INSTALL_TOKEN` to the app's own values to call `POST /v1/check`. A new `INSTALL_HASH` takes a seat. The server reply has only a status, not features or dates. The script shows that status but doesn't verify the reply's signature, so an app must use `check_online_reply` before trusting it. `gate.sh` returns false for `revoked`, `unknown`, `limit_reached` or an HTTP error. If the server can't be reached, the local license decides. On Windows, run the scripts in Git Bash and install `jq`.
- **Offline only:** the Python, Rust, Ruby and JS samples check the license file only. For the daily online check, use `evaluate()` from the verifiers.
