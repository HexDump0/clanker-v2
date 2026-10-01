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
