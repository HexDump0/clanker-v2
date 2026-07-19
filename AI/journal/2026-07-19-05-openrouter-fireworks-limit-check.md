# OpenRouter key and Fireworks limit check

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Queried OpenRouter's read-only current-key endpoint using the human-authorized key
  already configured in the gitignored `.env`. The key itself was never printed,
  stored, or copied into this journal.
- Made a minimal Fireworks-pinned DeepSeek V4 Flash request with reasoning disabled.
- Made two minimal Fireworks-pinned compatibility probes with reasoning enabled and
  `tool_choice=required` using a tiny synthetic output tool.
- No implementation code or configuration was changed.

## Why / decisions made
- The OpenRouter key is active, paid-tier, has a $3 non-resetting credit cap with almost
  all credit remaining, and has no meaningful key-level request cap exposed by the
  current-key endpoint. The endpoint's request-rate object is deprecated.
- Fireworks accepted the basic request.
- The first forced-tool + reasoning probe returned an upstream HTTP 429 with no
  `Retry-After`; an immediate equivalent retry returned HTTP 200. Therefore the key is
  not permanently blocked and Fireworks supports the required combination, but the
  route is subject to intermittent upstream throttling/capacity errors.
- Fireworks should only be used with bounded retry/backoff and a compatible fallback;
  it is unsafe as a no-fallback single provider for long reviews.

## Files touched
- `AI/journal/2026-07-19-05-openrouter-fireworks-limit-check.md` — created — records
  sanitized findings only.

## Open questions / for the human
- Which provider/model should be the fallback when Fireworks returns 429?
- Should the exposed key be rotated immediately despite its short expiry?

## Next steps
- Rotate the key because it was pasted into chat.
- Choose a fallback that supports the same output mode, or change DeepSeek reviews to
  prompted output so more providers are compatible.
