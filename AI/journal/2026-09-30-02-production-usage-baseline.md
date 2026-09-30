# Production usage baseline from Logfire

**Date:** 2026-09-30 · **Agent:** Claude Code (Opus 5.5) · **Type:** research

## What was done
- Queried the Logfire project `clanker-v2` (read-only) across the whole retained window
  (2026-08-31 → 2026-09-25, when production was stopped). Classified agent runs by their
  system instructions and aggregated volume, latency, rounds, tokens, cache hits, reasoning
  share, tool usage, verdict mix, and error types.
- Fetched current public OpenRouter per-provider prices for DeepSeek V4 Flash 0731.
- Wrote the findings to `AI/notes/production-usage-baseline-2026-09.md`.

## Why / decisions made
- The human asked for context on speed/cost optimization. Production was taken down after
  Hack Club AI access ended over resource usage, so the next deployment's cost will fall on
  the project itself.
- Key facts: about 134 reviews/day with nearly no chat. Reviews average 81–96k input tokens
  over 3.5 rounds. Round-1 cache hit is only 33%. Two-thirds of output is reasoning. The long
  tail is costly. Many tool calls re-fetch packet data. Vision/render sits on the critical
  path and has slow 429/timeout failure modes.

## Files touched
- `AI/notes/production-usage-baseline-2026-09.md` — created — baseline numbers.
- `AI/journal/2026-09-30-02-production-usage-baseline.md` — created — this entry.

## Open questions / for the human
- New provider and budget after Hack Club AI (direct OpenRouter key?).
- Is lowering reasoning effort or pinning a cheap provider acceptable, subject to a
  verdict-agreement check against past reviews?

## Next steps
- Agree on the target, then build a small replay eval from past certs before changing models,
  providers, or reasoning.
