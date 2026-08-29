# Update Stardance cookie v4 and retest integrations

**Date:** 2026-08-29 · **Agent:** Codex (GPT-5) · **Type:** fix

## What was done
- Retested Shipwrights, Stardance, and Slack after the owner refreshed credentials.
- Confirmed Slack bot auth, Socket Mode, channel/thread history, the newly added
  `users:read` scope, and display-name resolution all work.
- Confirmed Shipwrights remains blocked by Cloudflare before session authentication.
- Checked the current public Stardance source and found its cookie key is now
  `_stardance_session_4`; Clanker still used `_stardance_session_v3`.
- Updated the cookie constant/config help and added a regression test covering both a
  value-only setting and a full `_stardance_session_4=...` setting.

## Why / decisions made
- The refreshed v4 cookie value could never authenticate while Clanker sent it using
  the v3 cookie name.
- Old benchmark ship IDs are no longer sufficient to prove live access because they may
  have left the review queue. The deterministic request-cookie test proves the client
  now sends the current key; final live confirmation needs a current accessible ship.
- OpenRouter was intentionally not retested because the owner chose Hack Club AI; its
  configured review and vision calls passed in the preceding smoke test.

## Files touched
- `src/clanker/config.py` — modified — document current Stardance cookie name.
- `src/clanker/review/tools.py` — modified — send `_stardance_session_4`.
- `tests/test_review.py` — modified — regress cookie name and prefix handling.
- `AI/notes/live-tool-smoke-test-2026-08-29.md` — modified — correct diagnosis/status.
- `AI/journal/2026-08-29-07-stardance-v4-cookie-and-integration-retest.md` — created —
  this session record.

## Open questions / for the human
- A current Stardance ship ID is needed for final live confirmation while the dashboard
  remains inaccessible from this Cloudflare-blocked machine.
- The Shipwrights deployment/network still needs Cloudflare allowlisting or another
  access path before watcher and full-review testing can run here.

## Next steps
- Retest a current ship through `fetch_stardance_project` once its external ID is
  available, ideally after Shipwrights Cloudflare access is restored.
