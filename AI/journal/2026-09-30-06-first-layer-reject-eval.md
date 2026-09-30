# First-layer confident-reject eval with a holdout

**Date:** 2026-09-30 · **Agent:** Claude Code (Opus 5.5) · **Type:** research

## What was done
- Reframed the eval per the human: Clanker is the automated first layer that only rejects what it is
  confident about. Everything else passes to a human.
- Added `evals/jev/{evidence.py,questions_reject.py,report_layer.py,export_csv.py,
  thresholds.json,thresholds_conservative.json}`. Datasets are now split through `JEV_DATASET`
  (dev/holdout), and `export_traces.py --random N` produces a sample with the production mix.
- Tuned on dev (118). Fixed a conservative preset before running the holdout. Evaluated both once on a random
  holdout of 157 (Aug 31 – Sep 12). The export hit a DNS failure at 137 and the human asked to proceed
  on the traces available; a background chain is filling in the remaining traces toward 200.
- Results were appended to `AI/notes/jev-eval-results-2026-09-30.md`. OpenRouter spend so far is about $0.13.

## Why / decisions made
- The conservative preset gave 71 rejects at 89% precision, catching 52% of human rejects, with 8/35 good projects bounced.
  DeepSeek gave 55 rejects at 85%, catching 39%, with 8/35 bounced. Jev is about 30× cheaper and about 75× faster.
- Partial holdout results computed before the code excerpts existed were deleted and regenerated.

## Files touched
- `evals/jev/*` — see above. `AI/notes/jev-eval-results-2026-09-30.md` — appended.

## Open questions / for the human
- Drop or tighten the thin-README reason (it caused half the bounces)? That change must be validated on fresh data.
- The banner is not checkable by text. Should a cheap vision check be added?

## Next steps
- Rerun `report_layer.py` on the full 200 holdout once the export finishes.
- Production wiring: code facts, then one Jev call, then REJECT with fix text or pass to a human.
