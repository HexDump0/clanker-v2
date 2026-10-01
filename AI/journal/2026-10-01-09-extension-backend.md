# Extension backend: results store, local API, video upload

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** feature

## What was done
- Human asked for a browser extension: a Clanker tab on cert pages (judgement, reason, video, "use reason"/"use video"
  buttons), a page listing Clanker judgements for quick human confirm/overrule, and a "Clanker was wrong" feedback
  flow. Final decisions stay with a human. Human confirmed: "use video" should auto-upload and attach the video.
- This unit is the backend only. The extension itself is not built yet.
- `clanker.results`: one JSON per cert in `data/results/`, saved by `ReviewRunner.review_cert` (failure never
  fails a review). Holds verdict, reasons, reject message, video/pdf paths, human feedback, uploaded video URL.
  Re-reviews keep earlier feedback. Feedback exports as JSONL for evals.
- `clanker.api`: aiohttp on 127.0.0.1, bearer token (`EXTENSION_API_TOKEN`; off when unset). List/get results, serve the
  video, post feedback, export feedback, and `POST /api/results/{id}/upload-video`.
- `ShipwrightsClient.upload_proof_video`: the 3-step R2 upload from API.md. `[MUTATING]`, needs `allow_mutations`.
  Only the upload endpoint creates such a client, and only on a human click.

## Why / decisions made
- The API never calls submit-review. The extension fills the comment box; the human submits.
- Video upload is the one mutation the human explicitly approved (2026-10-01), triggered per click.
- `?token=` is accepted on the query string because `<video>` tags cannot send headers. Local-only, so acceptable.

## Files touched
- `src/clanker/{results.py,api.py}` created; `config.py`, `service.py`, `review/runner.py`,
  `shipwrights/client.py` modified; `.env.example`; `tests/test_extension_api.py` created. 223 tests pass.

## Open questions / for the human
- Chrome vs Firefox (assumed Chrome MV3). Does the dashboard review form need a specific DOM approach for filling?
- Is attaching a video allowed on a REJECT review in the dashboard flow, and does a second upload replace the first?

## Next steps
- Build the extension: judgements page first, then the cert-page tab, then feedback form.
