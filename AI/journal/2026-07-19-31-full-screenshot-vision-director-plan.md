# Full screenshot-first vision director plan

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** decision

## What was done
- Recorded the human-approved complete video workflow in the stable v2 architecture plan.
- Corrected the earlier candidate-ID design: the separate vision director sees clean
  evidence screenshots and returns exact visible text; code finds the containing element.
- Defined the required no-highlight fallback: bottom-right finding card with no spotlight.

## Why / decisions made
- Clean screenshots give the vision director the same visual evidence the viewer receives.
- Text-based selection keeps director output simple and general across arbitrary pages.
- Strict unique matching prevents a guessed, absent, or repeated text string from
  highlighting the wrong region.
- The director remains one-shot and tool-free; browser capture and matching stay
  deterministic and independently testable.

## Files touched
- `AI/context/v2-architecture-plan.md` — modified — updated the video agent boundary,
  workflow, contracts, and screenshot-first MVP.
- `AI/journal/2026-07-19-31-full-screenshot-vision-director-plan.md` — created — this entry.

## Open questions / for the human
- Concrete vision provider/model and its image-count/size limits.
- Final caps; proposed defaults remain five candidate screenshots, three output scenes,
  and 25 seconds.

## Next steps
- Implement contracts and capture snapshots, then benchmark exact-text selection with the
  chosen vision model using the ferrocompiler PDF and additional frozen evidence fixtures.
