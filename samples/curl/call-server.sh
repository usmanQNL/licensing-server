#!/usr/bin/env bash
# Ask a running server-side gate sample (Python, Node, Ruby or Rust) for the plan, then call a
# gated route. The server decides: HTTP 200 if the license includes the feature, 403 if not.
#
#   ./call-server.sh [base-url] [path]
#   ./call-server.sh http://localhost:8000 /reports/pdf
set -uo pipefail
base="${1:-http://localhost:8000}"
route="${2:-/reports/pdf}"

echo "Plan (GET $base/license/plan):"
curl -sS "$base/license/plan"; echo

echo "Gated route (GET $base$route):"
curl -sS -w '\nHTTP %{http_code}\n' "$base$route"
