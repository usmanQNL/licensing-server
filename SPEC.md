# Licensing spec (v1)

Shared by every language verifier, the issuer, and the online-check server.
Any implementation must pass the shared fixtures before it ships: `verifiers/cases.json` (license files) and `verifiers/online-replies.json` (server replies, with `verifiers/online-public.pem`).

## 1. License file

A JSON object with `kid`, `payload`, and `signature`.

```json
{
  "kid": "k1",
  "payload": {
    "v": 1,
    "license_id": "LIC-2026-0001",
    "customer": "Example Ltd",
    "plan": "subscription",
    "features": ["sso", "hourly_sync"],
    "max_installs": 1,
    "issued_at": "2026-11-10T00:00:00Z",
    "expires_at": "2027-11-10T00:00:00Z"
  },
  "signature": "base64url-ed25519-signature"
}
```

- `kid` names the signing key. Verifiers pick the matching trusted key.
- `max_installs` is the seat limit. It's enforced by the online check. Default 1 if missing.

- `plan` is one of `opensource`, `subscription`, `gated`.
- `full` was merged into `subscription`. Licenses issued as `full` still verify, because the verifiers treat `full` as an alias of `subscription`.
- `features` is used by `gated` mode. Other modes may leave it empty.
- `application` is not in the file. It's used for the output folder and the Firestore record.
- `expires_at` is absent for perpetual licenses (`opensource`, or a perpetual `gated` license).
- Times are UTC, RFC 3339, with a `Z` suffix.

### Signing
- Algorithm: Ed25519.
- The signed bytes are the canonical JSON of `payload`: keys sorted, no insignificant whitespace, UTF-8.
- `signature` is base64url without padding.
- Verifiers reject any file whose `v` they do not understand.

## 2. Keys

- One Ed25519 key pair per product, identified by a `kid`.
- The public key ships inside the app (`license-public.pem` or a language constant). Never a secret.
- Apps may trust several keys at once as `{kid: PEM}`. This allows rotation without breaking installed apps. Rotation steps: README, "Key rotation".
- The private key stays out of git (gitignored). It lives on the issuer's machine or in a secret manager. The server reads it from the secret manager, never from the repo.

### 2a. Signed key list (v1)

- The app bakes in one root public key (`root-public.pem`). It never changes. `sign_keylist.py init-root` creates it, next to the root private key.
- `keys.json` holds only public keys (one PEM per kid). `sign_keylist.py make-keys` adds them, and no private key is copied.
- `GET {endpoint}/v1/keys` returns a key list signed by the root key: `{"kid": "root", "payload": {"v": 1, "issued_at", "keys": {kid: PEM}, "revoked": [kid]}, "signature"}`.
- The app verifies the list with the root key, caches it, and uses the cache when the network is down. A copy shipped with the app covers the first run.
- Rotation: add the new kid to the list, upload it, then issue licenses with the new kid. Apps trust it without an update.
- `revoked` kids are no longer trusted.
- The root private key stays offline (`sign_keylist.py`). The server only serves the signed file and never holds the root key.

## 3. Verification rules (apply in this order)

1. Parse the file. Reject if malformed.
2. Pick the trusted key for `kid`. Reject if no key matches. With a single key and no `kid`, use that key.
3. Verify the signature. Reject if invalid.
4. Check `v` is supported.
5. Check the plan matches the build's mode.
6. Check expiry (see section 4).
7. For `gated`, check the requested feature is in `features`.

Failure at any step means the license is treated as absent, and only paid features are disabled. Sign-in is never blocked.

When the app also has an online reply, combine them (section 8, `evaluate`).

## 4. Expiry and grace period

- `expires_at` in the past starts the grace period.
- Default grace period: 14 days. Configurable per product.
- During grace, paid features still work, and the app shows a warning with the expiry date.
- After grace, paid features turn off. Free features always stay on.

## 5. Online check (optional, on by default)

Users can turn it off. The skill asks for the server endpoint URL at setup.

- Once per day, the app sends `{license_id, install_hash}` to `POST {endpoint}/v1/check`. After activation, it also sends `install_token`.
- `install_hash` is a random ID generated once per install and stored locally. It is not personal data. No names, emails, or machine identifiers.
- The first check from an install that gets a free seat returns an `install_token` in the reply, once. The app stores it. Every later check must send it, or the server returns HTTP 403.
- The server replies with a signed status:

```json
{
  "kid": "k1",
  "payload": {
    "v": 1,
    "license_id": "LIC-2026-0001",
    "status": "active",
    "max_installs": 1,
    "checked_at": "2026-11-10T05:00:00Z",
    "valid_until": "2026-11-17T05:00:00Z"
  },
  "signature": "..."
}
```

On first activation the payload also has `install_token`.

- `status` is `active`, `revoked`, `unknown`, or `limit_reached` (this install is beyond the license's `max_installs`).
- The app verifies the reply with the same public key. It does not trust unsigned data.
- The app caches the last valid signed reply. A failed or unreachable check uses the cache.
- A cached reply expires at `valid_until`. Past that time, the app falls back to the grace-period rules.
- `revoked`, `unknown`, and `limit_reached` disable paid features at the next successful check. There is no instant kill.
- Clock guard: the app stores the newest time it has seen (`last_seen`). If the clock is more than 5 minutes behind it, paid features turn off until the clock is corrected.
- Network errors never block sign-in.

## 6. Server API (v1)

- `POST /v1/check`: body as above (`install_token` optional). Returns a signed status payload.
  - HTTP 403: a known install sent no token, or a wrong one.
  - HTTP 413: body over 2 KB.
  - HTTP 429: more than 60 checks a minute from one client (configurable).
- `GET /v1/health`: returns `{"ok": true}`, no auth.
- `GET /v1/keys`: returns the signed key list (section 2a), no auth. HTTP 503 if the server has no key list configured.
- No endpoint lists or edits licenses. Management happens in the storage console or through the storage adapter.

Storage (vendor-neutral):
- `licenses` collection: `license_id`, `status` (`active`, `revoked`), `plan`, `customer`, `application`, `features`, `max_installs`, `issued_at`, `expires_at`, `client_email`, `client_phone`. The contact fields are never written to license files or replies.
- `installs` collection: `license_id`, `install_hash`, `first_seen`, `last_seen`, `token_hash` (SHA-256 of the install token, never the token itself).
- Adapters: Firestore (first), plus JSON file for local tests. Others can be added (README, "Use another database").

## 7. Versioning

Every file and reply has `v`. Bump it only for breaking changes. Verifiers must reject unknown versions rather than guess.

## 8. Decisions and checks (v1)

- **kid:** every license file and server reply has a `kid` next to `payload` and `signature`. Verifiers accept one PEM, or a map `{kid: PEM}` for key rotation. An unknown `kid` is rejected.
- **max_installs:** each license has `max_installs` (default 1). The server counts distinct install hashes and returns `limit_reached` for a new install beyond the limit.
- **Combined decision (`evaluate`):** the local license must be valid. A fresh online reply of `revoked`, `unknown`, or `limit_reached` turns paid features off. With no reply, or a reply past `valid_until`, the local license decides, so offline use still works.
- **Reply freshness:** a reply is trusted only until its `valid_until`. Cached replies are never extended.
- **Install tokens:** the first check for a new install with a free seat returns an `install_token` in the signed reply, once. The server stores only its SHA-256 hash. Every later check for that install must send the token, or the server returns HTTP 403. A guessed or copied install hash can't use someone else's seat. A leaked license file can still use up seats, so this is not a full defence.
- **Clock guard:** the app stores the newest time it has seen (`last_seen`) and passes it to the verifier. If the clock is more than 5 minutes behind `last_seen`, paid features turn off until the clock is corrected. Store the maximum of the current time after each check.

## 9. Open items

- Exact feature names per product are chosen by the skill user.
- Dart verifier is untested. Rust and the Python and Node verifiers pass the shared fixtures.
