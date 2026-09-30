# Jev (TypeSafe) research for review decisions

**Date:** 2026-09-30 · **Agent:** Claude Code (Opus 5.5) · **Type:** research

## What was done
- Read the TypeSafe docs index and the key pages. Checked the OpenRouter catalog for Jev.
- Made one probe to OpenRouter `typesafe/jev-router` with the `.env` key. It returned 401 "API key
  expired" and no tokens were spent. No other external calls were made.
- Wrote `AI/notes/jev-typesafe-evaluation-2026-09-30.md`, covering capabilities, limits, fit, and an eval
  design.

## Why / decisions made
- The human wants Jev to make the review decision so it's cheaper and faster, while the owner pays
  for everything. Jev is a typed-decision model: it can't call tools or generate text, has a
  32k state limit, and is weak on dates, counting, and adversarial content. It can replace the verdict
  step but not the investigation or the fix/feedback writing.
- Proposed evaluating against human per-attempt verdicts, using frozen evidence replayed from
  Logfire. This addresses the human's point that a previous reject may be an approve now.

## Files touched
- `AI/notes/jev-typesafe-evaluation-2026-09-30.md` — created.
- `AI/journal/2026-09-30-03-jev-typesafe-research.md` — created.

## Open questions / for the human
- Needs a fresh OpenRouter key and a TypeSafe API key.
- May the eval make read-only Dashboard GETs to collect human verdicts per attempt?
- Hybrid shape: should deterministic plus Jev-guided investigation replace the agentic loop, or
  should the LLM investigate and Jev only decide?
