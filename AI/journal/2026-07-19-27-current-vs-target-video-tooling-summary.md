# Current versus target video tooling summary

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** decision

## What was done
- Summarized the present benchmark pipeline and the proposed production PDF-to-video
  pipeline for arbitrary Shipwright reviews.

## Why / decisions made
- Preserve the key boundary: the model selects and words evidence scenes; deterministic
  code owns PDF extraction, browsing, capture, visual design, rendering, validation, and
  failure handling.

## Files touched
- `AI/journal/2026-07-19-27-current-vs-target-video-tooling-summary.md` — created — records
  this summary.

## Open questions / for the human
- None.

## Next steps
- Generalize the benchmark only after the human approves this division of responsibility.
