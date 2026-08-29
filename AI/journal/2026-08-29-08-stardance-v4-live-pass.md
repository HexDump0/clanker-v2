# Confirm Stardance v4 cookie works live

**Date:** 2026-08-29 · **Agent:** Codex (GPT-5) · **Type:** fix

## What was done
- Retested `fetch_stardance_project` after the owner installed a v4 Stardance session
  value and Clanker was updated to send `_stardance_session_4`.
- Successfully fetched three authenticated ship pages, each with structured metadata
  and visible page text.
- Updated the durable smoke-test note from 13/14 to 14/14 registered review tools passing.

## Why / decisions made
- Three separate successful pages rule out a stale single fixture and confirm both the
  refreshed value and corrected cookie name work in the real tool.
- Shipwrights remains a separate Cloudflare network block; the Stardance success does
  not change that diagnosis.

## Files touched
- `AI/notes/live-tool-smoke-test-2026-08-29.md` — modified — record final live pass and
  remove resolved Stardance/Slack actions.
- `AI/journal/2026-08-29-08-stardance-v4-live-pass.md` — created — this record.

## Open questions / for the human
- Shipwrights Cloudflare access remains unresolved from this machine.

## Next steps
- Resolve or allowlist this runtime at `ds.shipwrights.dev`, then rerun the read-only
  dashboard and full review-pipeline smoke tests.
