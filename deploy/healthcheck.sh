#!/usr/bin/env sh
set -eu

ui_url=${METRON_UI_URL:-http://127.0.0.1:3000}
api_url=${METRON_API_URL:-http://127.0.0.1:8000}

curl --fail --silent --show-error "$ui_url/" >/dev/null
curl --fail --silent --show-error "$api_url/healthz" >/dev/null

printf '%s\n' "PASS: dashboard and API health endpoints responded"
