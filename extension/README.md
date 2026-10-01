# Clanker for Shipwrights (Chrome + Firefox)

Plain MV3 JavaScript, no build step. The same folder loads in both browsers.

## Run it
1. In `.env`: `EXTENSION_API_ENABLED=true`, then `uv run clanker run` (API on http://127.0.0.1:8765).
2. **Chrome:** `chrome://extensions` → Developer mode → Load unpacked → pick `extension/`.
   **Firefox:** `about:debugging#/runtime/this-firefox` → Load Temporary Add-on → pick `extension/manifest.json`.
3. Be logged in to ds.shipwrights.dev. Click the toolbar icon for the judgements page; open a ship Clanker judged to get the panel.
4. Hosted later: judgements page → Settings → set the API URL (https). Chrome asks for host permission when needed.

## How it works
- Auth: the background script reads your dashboard `session` cookie and sends it as a bearer token. The API only validates it
  (one read-only dashboard call) and never stores or reuses it.
- **Use reason** fills the dashboard's "Write feedback for the submitter…" box. You read it and submit yourself.
- **Use video** downloads the video from Clanker and runs the dashboard's own 3-step upload (presign, PUT, attach) from the
  page with your session, then reloads. The server never uploads anything.
- **Clanker was right/wrong** saves feedback on the result; "Export feedback" on the judgements page downloads JSONL.
- **Request / Re-request Clanker review** runs a review on the server (ships Clanker hasn't seen, or a fresh look at one it has).
  One run per ship at a time, 60s cooldown, shares the review concurrency limit. A new result clears an old right/wrong label
  if the verdict or reasons changed.

## Packaging / installing for real
`extension/build.sh` writes `dist/clanker-chrome.zip` and `dist/clanker-firefox.xpi` (same contents).
- **Chrome / Chromium:** Load unpacked works forever for your own use. A `.crx` outside the Web Store is blocked on
  Windows/macOS; to share it, upload the zip to the Chrome Web Store (unlisted is fine, $5 one-time developer fee).
- **Firefox:** release Firefox only installs *signed* add-ons. Options: (a) sign it as **unlisted** on addons.mozilla.org
  (free; `npx web-ext sign --channel=unlisted --api-key=… --api-secret=…` with keys from the AMO developer hub), then open the
  signed `.xpi`; (b) use Firefox Developer Edition/Nightly with `xpinstall.signatures.required=false`; (c) temporary
  loading from `about:debugging` (cleared on restart).
- **Sidebar "Clanker" entry** (`nav.js`): clones an inactive sidebar link and appends it under "My Balance". Clicking it covers
  the dashboard's main panel with the judgements page (an iframe of the extension page, `web_accessible_resources`). Another
  sidebar link, a route change or Esc closes it.

## Design
Styled from the dashboard's own "graphite" theme tokens (`ui.css`), with Geist / Geist Mono / Space Grotesk bundled in
`fonts/` for the extension page. `ui.js` holds the shared result view used by both the judgements page and the cert panel.
Judgements page: master/detail triage with filters, search, keyboard shortcuts (`j`/`k` move, `r` right, `w` wrong),
"Review a ship" (paste a link or ID) and a settings dialog that tests the API connection.
