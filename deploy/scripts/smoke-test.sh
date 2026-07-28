#!/bin/sh
set -eu

base_url=${1:-http://127.0.0.1:8080}
temporary_dir=$(mktemp -d "${TMPDIR:-/tmp}/aemet-radar-smoke.XXXXXX")
trap 'rm -rf "$temporary_dir"' EXIT HUP INT TERM

curl --fail --silent --show-error "$base_url/healthz" >/dev/null
curl --fail --silent --show-error "$base_url/" >"$temporary_dir/index.html"
curl --fail --silent --show-error \
    "$base_url/radar/index.json" >"$temporary_dir/radar-index.json"
curl --fail --silent --show-error \
    "$base_url/status/health.json" >"$temporary_dir/health.json"

grep -q '<div id="root">' "$temporary_dir/index.html"
jq -e \
    '.schemaVersion == 1 and (.radars | type == "array") and (.radars | length > 0)' \
    "$temporary_dir/radar-index.json" >/dev/null
jq -e \
    '.schemaVersion == 1 and (.products | type == "array") and (.products | length > 0)' \
    "$temporary_dir/health.json" >/dev/null

printf 'Smoke test correcto: %s\n' "$base_url"
jq '{generatedAt, status, products: (.products | length)}' \
    "$temporary_dir/health.json"
