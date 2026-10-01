#!/usr/bin/env bash
# Package the extension. The same zip works for Chrome (Web Store upload) and Firefox (.xpi).
set -euo pipefail
cd "$(dirname "$0")"
rm -rf ../dist && mkdir -p ../dist
npx --yes web-ext build --source-dir . --artifacts-dir ../dist --overwrite-dest \
  --ignore-files build.sh README.md >/dev/null
zip=$(ls ../dist/*.zip | head -1)
cp "$zip" ../dist/clanker-firefox.xpi
mv "$zip" ../dist/clanker-chrome.zip
ls -l ../dist
