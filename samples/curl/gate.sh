#!/usr/bin/env bash
# Licensing Gate from the command line: prints true or false. Exit code 0 for true, 1 for false.
#
#   ./gate.sh <feature> [license.json] [public.pem]
#
# Uses plan.sh, so the same tools and the same optional server settings apply
# (LICENSE_SERVER, INSTALL_HASH, INSTALL_TOKEN). When the server is set and answers
# revoked, unknown or limit_reached, the gate is false.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
feature="${1:?usage: ./gate.sh <feature> [license.json] [public.pem]}"
features_file="$(mktemp)"; trap 'rm -f "$features_file"' EXIT
jq -cn --arg f "$feature" '[$f]' > "$features_file"

enabled=$("$here/plan.sh" "${2:-$here/../demo/license-gated.json}" "${3:-$here/../demo/demo-public.pem}" "$features_file" \
  | jq '.features[0].enabled and (.server_status == null or .server_status == "active" or .server_status == "unreachable")')
echo "$enabled"
[[ "$enabled" == true ]]
