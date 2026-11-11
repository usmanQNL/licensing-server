#!/usr/bin/env bash
# Licensing Plan from the command line: prints the installed license plan as JSON.
#
#   ./plan.sh [license.json] [public.pem] [features.json]
#
# curl alone can't check an Ed25519 signature, so the local check uses openssl (3.0+) and jq.
# curl is used for the optional live status from your server (POST /v1/check). Set these to
# turn it on. Use the app's own install_hash and install_token: a new install_hash takes a seat.
#   LICENSE_SERVER=https://your-service-url  INSTALL_HASH=...  INSTALL_TOKEN=...
#
# Needs: bash, jq, openssl 3, curl. On Windows, run it in Git Bash and install jq.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
license="${1:-$here/../demo/license-gated.json}"
pubkey="${2:-$here/../demo/demo-public.pem}"
features="${3:-$here/../demo/features.json}"

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

# 1. Verify the signature over the canonical payload (keys sorted, no whitespace).
sig_ok=false
if jq -e '.payload and .signature' "$license" >/dev/null 2>&1; then
  jq -cjS '.payload' "$license" > "$tmp/payload"
  jq -rj '.signature' "$license" | tr '_-' '/+' > "$tmp/sig.b64"
  pad=$(( (4 - $(wc -c < "$tmp/sig.b64") % 4) % 4 )); printf '%*s' "$pad" '' | tr ' ' '=' >> "$tmp/sig.b64"
  base64 -d "$tmp/sig.b64" > "$tmp/sig" 2>/dev/null || true
  if openssl pkeyutl -verify -pubin -inkey "$pubkey" -rawin -in "$tmp/payload" -sigfile "$tmp/sig" >/dev/null 2>&1; then
    sig_ok=true
  fi
fi

# 2. Optional live status from the server. It returns status only (no features or dates).
server_status=null
if [[ -n "${LICENSE_SERVER:-}" && -n "${INSTALL_HASH:-}" && "$sig_ok" == true ]]; then
  body=$(jq -cn --arg id "$(jq -r '.payload.license_id' "$license")" --arg h "$INSTALL_HASH" --arg t "${INSTALL_TOKEN:-}" \
    '{license_id: $id, install_hash: $h} + (if $t == "" then {} else {install_token: $t} end)')
  # The reply is signed. This script shows its status but does not verify that signature;
  # an app must verify it with its verifier (check_online_reply) before trusting it.
  # Network failure gives "unreachable" (the local license decides, like offline use).
  # An HTTP error gives "http_<code>", for example http_403 when INSTALL_TOKEN is missing or wrong.
  code=$(curl -sS -o "$tmp/reply" -w '%{http_code}' -X POST "${LICENSE_SERVER%/}/v1/check" \
    -H 'Content-Type: application/json' -d "$body" 2>/dev/null) || code=000
  if [[ "$code" == 200 ]]; then server_status=$(jq -c '.payload.status' "$tmp/reply")
  elif [[ "$code" == 000 ]]; then server_status='"unreachable"'
  else server_status="\"http_$code\""; fi
fi

# 3. Build the plan JSON. Same fields and rules as the other samples.
jq -n --argjson ok "$sig_ok" --slurpfile all "$features" --argjson doc "$(jq -c . "$license" 2>/dev/null || echo '{}')" --argjson server "$server_status" '
  (($doc | objects | .payload | objects) // {}) as $p
  | (if $ok and $p.v != 1 then "unsupported license version"
     elif $ok and (["opensource","subscription","gated","full"] | index($p.plan)) == null then "unknown plan"
     elif $ok then null else "invalid or unreadable license" end) as $bad
  | (if $bad then {} else $p end) as $p
  | (if $p.plan == "full" then "subscription" else $p.plan end) as $plan
  | (if $bad == null and ($plan == "subscription" or $plan == "gated") and $p.expires_at then
       ($p.expires_at | fromdateiso8601) as $exp
       | if now > $exp + 14*86400 then "expired" elif now > $exp then "grace" else "active" end
     elif $bad == null then "active" else "invalid" end) as $status
  | ($status == "active" or $status == "grace") as $valid
  | ($p.features // []) as $lic
  | {
      valid: $valid,
      status: $status,
      reason: ($bad // {active: "valid", grace: "in grace period", expired: "license expired"}[$status]),
      license_id: $p.license_id, customer: $p.customer,
      name: (if $p == {} then null else $plan end),
      start: $p.issued_at, expires: $p.expires_at,
      perpetual: ($p != {} and ($p | has("expires_at") | not)),
      max_installs: (if $p == {} then null else ($p.max_installs // 1) end),
      features: [($all[0] + (($lic - $all[0]) | sort))[] | {name: ., enabled: ($valid and ($plan == "subscription" or (. as $f | $lic | index($f)) != null))}],
      server_status: $server
    }'
