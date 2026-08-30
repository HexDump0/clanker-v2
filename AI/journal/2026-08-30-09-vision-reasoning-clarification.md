# Vision reasoning clarification

**Date:** 2026-08-30 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Compared the pre-change vision-agent settings with the current implementation to
  answer whether vision reasoning had already been disabled.

## Why / decisions made
- Confirmed the old vision agent set only a timeout and did not explicitly control
  reasoning. Its old model was the reasoning-specific
  `qwen/qwen3-vl-8b-thinking`, so reasoning was effectively expected rather than
  disabled.
- Explicit `reasoning.enabled=false` was introduced with the Qwen3.8 Flash switch after
  a live small-output probe spent its entire completion budget on reasoning and returned
  no visible description.
- No code or configuration was changed in this clarification.

## Files touched
- `AI/journal/2026-08-30-09-vision-reasoning-clarification.md` — created — records the
  answer and evidence.

## Open questions / for the human
- None.

## Next steps
- None unless the human prefers vision reasoning enabled despite the latency/output
  overhead.
