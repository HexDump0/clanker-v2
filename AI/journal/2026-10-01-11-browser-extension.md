# Browser extension (Chrome + Firefox)

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** feature

## What was done
- `extension/`: MV3, no build step, one folder for Chrome and Firefox (manifest has `service_worker` + `scripts`;
  `web-ext lint`: 0 errors, 2 expected warnings).
  - `content.js`: Clanker panel on `ds.shipwrights.dev/*/certifications/*` (judgement, reasons, shipper message, video, Use reason,
    Use video, right/wrong feedback). SPA navigation handled by polling the URL.
  - `judgements.html/js`: triage list with verdict filters, lazy video, right/wrong, JSONL export, API URL setting.
  - `background.js`: reads the HttpOnly `session` cookie (only the background can) for the bearer token.
- Learned from the live dashboard (read-only, human-authorized token use): the review box is
  `textarea[placeholder^="Write feedback for the submitter"]` (React-controlled; filled via `execCommand('insertText')`), and the
  dashboard's own upload sends `filename, contentType, size` then PUTs from the browser, so the extension mirrors that exactly.
- Moved video upload out of the server: removed `upload_proof_video` and the API upload endpoint (hosted, the server would have
  used its owner's session). Also removed the `?token=` query fallback; the video is fetched as a blob with the header.
- Smoke test against the real dashboard: real token validates (200), bad token 401.

## Not verified
- The extension has not been loaded in a real browser here. Needs a manual pass: panel renders, Use reason fills the box (only
  present once the ship is claimed/IN_REVIEW), Use video attaches and the dashboard shows it, R2 PUT is accepted from a content script.

## Files touched
- `extension/*` created; `src/clanker/{api.py,results.py,shipwrights/client.py}` and `tests/test_extension_api.py` trimmed.

## Next steps
- Manual browser pass; icons; host the API behind TLS; use feedback JSONL in the evals.
