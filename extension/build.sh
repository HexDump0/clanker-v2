#!/usr/bin/env bash
# Package the extension (the same zip works for Chrome and, as .xpi, Firefox).
#   ./build.sh                                   local default API (http://127.0.0.1:8765)
#   API_URL=https://clanker.example.com ./build.sh   bake your hosted URL in as the default
#   AMO_API_KEY=… AMO_API_SECRET=… API_URL=… ./build.sh --sign    also sign for Firefox (unlisted, addons.mozilla.org)
set -euo pipefail
cd "$(dirname "$0")"
stage=$(mktemp -d); trap 'rm -rf "$stage"' EXIT
cp -r . "$stage/"
rm -f "$stage/build.sh" "$stage/README.md"

if [ -n "${API_URL:-}" ]; then
  python3 - "$stage" "$API_URL" <<'PY'
import json, pathlib, re, sys
from urllib.parse import urlparse
stage, url = pathlib.Path(sys.argv[1]), sys.argv[2].rstrip("/")
u = urlparse(url)
if u.scheme not in ("https", "http") or not u.netloc:
    sys.exit(f"API_URL must look like https://host, got {url!r}")
api = stage / "api.js"
src = api.read_text()
out = re.sub(r'const DEFAULT_BASE = "[^"]*";', f'const DEFAULT_BASE = "{url}";', src)
if out == src:
    sys.exit("could not find DEFAULT_BASE in api.js")
api.write_text(out)
manifest = stage / "manifest.json"
m = json.loads(manifest.read_text())
origin = f"{u.scheme}://{u.netloc}/*"
if origin not in m["host_permissions"]:
    m["host_permissions"].append(origin)
manifest.write_text(json.dumps(m, indent=2) + "\n")
print(f"default API set to {url}")
PY
fi

rm -rf ../dist && mkdir -p ../dist
npx --yes web-ext build --source-dir "$stage" --artifacts-dir ../dist --overwrite-dest >/dev/null
zip=$(ls ../dist/*.zip | head -1)
cp "$zip" ../dist/clanker-firefox.xpi
mv "$zip" ../dist/clanker-chrome.zip

if [ "${1:-}" = "--sign" ]; then
  : "${AMO_API_KEY:?set AMO_API_KEY}" "${AMO_API_SECRET:?set AMO_API_SECRET}"
  npx --yes web-ext sign --source-dir "$stage" --artifacts-dir ../dist/signed --channel unlisted \
    --api-key "$AMO_API_KEY" --api-secret "$AMO_API_SECRET"
  echo "signed .xpi is in dist/signed/"
fi
ls -l ../dist
