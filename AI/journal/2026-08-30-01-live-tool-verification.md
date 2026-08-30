# Live agent-tool verification pass (all green)

**Date:** 2026-08-30 · **Agent:** opencode (GLM) · **Type:** research

## What was done
- Re-ran a live, read-only smoke test of every registered review-agent tool using the
  repo's current `.env`. No secret values were printed or persisted; no mutating
  Dashboard endpoints, Slack writes, reviews, claims, or verdict submissions were made.
- 15/15 registered review tools pass live: all 8 GitHub tools (authenticated, incl. code
  search), `check_url`, `fetch_page_text`, `render_page` (Chromium + vision model),
  `check_package`, `web_search` (Exa proxy), `fetch_stardance_project`, and
  `fetch_stardance_devlog` (live project 34363, devlog 27822 — parsed 2 devlogs with
  structured `summary`/`completeness` metadata).
- Supporting integrations verified:
  - Shipwrights Dashboard reads (`list_certifications`, `get_feedback_templates`) — PASS.
    The Cloudflare 403 block from 2026-08-29 is **gone**; ordinary HTTPX requests return
    JSON 200 (50 certs page 1 of 206, 10259 total). This unblocks `run_review` and the
    watcher from this machine.
  - Slack: `auth.test`, `apps.connections.open`, `conversations.history` — all PASS.
  - Hack Club review model ping (`deepseek/deepseek-v4-flash`) — PASS. It is a reasoning
    model: a probe with `max_tokens=10` returned empty content because reasoning tokens
    consumed the budget; with adequate budget it answers correctly (`finish_reason=stop`).
  - OpenRouter `/api/v1/key` — still HTTP 401 (`API key expired.`). Known state, not
    blocking (`AI_PROVIDER=hackclub`).
- Test driver script lived in `/tmp/opencode` (not committed).

## Why / decisions made
- Stardance project URLs are not discoverable via Exa (site not indexed) and are absent
  from cert `demo_url`/`repo_url` fields and the first 12 cert READMEs; live URLs were
  recovered from the sanitized HAR archive in `har/` instead.
- The stardance session cookie still works (`_stardance_session_4`), confirmed by a live
  authenticated project fetch plus same-origin redirect behavior.

## Files touched
- `AI/notes/live-tool-smoke-test-2026-08-30.md` — created — updated live results.
- `AI/journal/2026-08-30-01-live-tool-verification.md` — created — this record.

## Open questions / for the human
- Replace `OPENROUTER_API_KEY` if direct OpenRouter use may be enabled later (still 401).

## Next steps
- With the Cloudflare block resolved, a human-observed full `run_review` pipeline pass is
  now possible to evaluate the enriched evidence packet end to end.

## Verification
- All checks above were executed live against real endpoints on 2026-08-30, read-only.
