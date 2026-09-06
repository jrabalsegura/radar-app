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
    '.schemaVersion == 1 and (.radars | type == "array") and (.radars | length == 16)' \
    "$temporary_dir/radar-index.json" >/dev/null
jq -e \
    '.schemaVersion == 1 and (.products | type == "array") and (.products | length == 16)' \
    "$temporary_dir/health.json" >/dev/null

# Comprueba todos los manifiestos y cada URL distinta que anuncian, incluidas coberturas.
jq -r '.radars[].manifestUrl' "$temporary_dir/radar-index.json" >"$temporary_dir/manifests"
while IFS= read -r manifest_url; do
    case "$manifest_url" in /radar/*/manifest.json) ;; *) exit 1 ;; esac
    curl --fail --silent --show-error --max-time 20 \
        "$base_url$manifest_url" >"$temporary_dir/manifest.json"
    jq -e '.schemaVersion == 1 and .window.minutes == 230 and (.frames | type == "array")' \
        "$temporary_dir/manifest.json" >/dev/null
    jq -r '.frames[] | .imageUrl, (.noCoverageUrl // empty)' \
        "$temporary_dir/manifest.json" >>"$temporary_dir/images"
done <"$temporary_dir/manifests"
if test -f "$temporary_dir/images"; then
    sort -u "$temporary_dir/images" >"$temporary_dir/unique-images"
    while IFS= read -r image_url; do
        case "$image_url" in /radar/*/frames/*.png|/radar/*/frames/*.webp) ;; *) exit 1 ;; esac
        curl --fail --silent --show-error --head --max-time 20 \
            "$base_url$image_url" >"$temporary_dir/image-headers"
        grep -qi '^Content-Type: image/' "$temporary_dir/image-headers"
        grep -qi '^Cache-Control:.*immutable' "$temporary_dir/image-headers"
    done <"$temporary_dir/unique-images"
fi
# Los originales no deben exponerse mediante el frontend.
test "$(curl --silent --output /dev/null --write-out '%{http_code}' "$base_url/raw/probe.gif")" = 404

printf 'Smoke test correcto: %s\n' "$base_url"
jq '{generatedAt, status, products: (.products | length)}' \
    "$temporary_dir/health.json"
