# Live smoke-test every Clanker review tool

**Date:** 2026-08-29 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Inventoried all 14 functions registered by `ReviewTools.all()` and the three extra
  chat tools (`run_review`, `remember`, and `forget`).
- Ran safe live calls for every primitive review tool using current `.env` credentials,
  a public GitHub repository, a public web page, PyPI, known Stardance ship IDs, and a
  small web-search query.
- Tested the configured review model, vision model, direct OpenRouter key, Shipwrights
  read access, Slack bot authentication, Socket Mode token, configured-channel/thread
  history, Slack display-name lookup, temporary memory operations, and Typst PDF output.
- Diagnosed failures without printing credentials or making external mutations.

## Why / decisions made
- Slack posts/uploads and Shipwrights mutations were not used because a health test does
  not justify changing live external state. Their relevant scopes/guards were inspected.
- `run_review` was not forced after its required Shipwrights read dependency was proven
  blocked by Cloudflare; doing so would only reproduce the same failure and spend no
  useful model work.
- Multiple known ship IDs and with/without-cookie comparisons were used to distinguish a
  Stardance authentication problem from one stale fixture ID.
- Dashboard requests were compared with and without the session cookie. Identical
  Cloudflare block pages show that the request is denied before application-level
  session validation, so no claim is made about whether that cookie itself is current.

## Files touched
- `AI/notes/live-tool-smoke-test-2026-08-29.md` — created — full sanitized result matrix
  and remediation list.
- `AI/journal/2026-08-29-06-live-tool-smoke-test.md` — created — this session record.

## Open questions / for the human
- Which deployment IP/user-agent should be allowed through the Shipwrights Cloudflare
  policy?
- Whether direct OpenRouter is intended as an active fallback despite
  `AI_PROVIDER=hackclub`.
- Whether Slack display-name resolution matters enough to add `users:read` and reinstall
  the app.

## Next steps
- Refresh the Stardance cookie, replace the expired OpenRouter key if needed, add the
  optional Slack scope, and retest Shipwrights from an allowed network/deployment.
