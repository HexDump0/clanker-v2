# Model inventory with video disabled

**Date:** 2026-08-30 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Traced the `VIDEO_ENABLED` and `BROWSER_RENDER_ENABLED` gates through application
  construction, packet enrichment, and the review runner.
- Clarified which configured models remain active when video generation is disabled.

## Why / decisions made
- `VIDEO_ENABLED=false` prevents construction and invocation of the Nex-N2-Mini video
  director, but does not disable screenshot analysis; browser rendering is an independent
  review-evidence feature.
- With the current settings, the remaining unique models are DeepSeek V4 Flash for
  review/chat/daily praise and Qwen3-VL-8B-Thinking for demo screenshot description.
- No code or configuration was changed.

## Files touched
- `AI/journal/2026-08-30-07-disabled-video-models.md` — created — records the clarified
  runtime behavior.

## Open questions / for the human
- Should screenshot vision remain enabled for review quality, or should the upcoming
  speed work benchmark disabling/replacing it independently?

## Next steps
- If optimizing the non-video path, measure DeepSeek review time separately from the
  concurrently pre-fetched browser render and Qwen screenshot-description time.
