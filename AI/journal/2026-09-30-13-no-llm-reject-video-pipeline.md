# No-LLM rejection video: pipeline entry point

**Date:** 2026-09-30 · **Agent:** Claude Code (Opus 5.5) · **Type:** feature

## What was done
- `pipeline.py` refactor: capture and compose/render/manifest are now shared helpers
  (`_capture_all`, `_compose_and_render`). The LLM-director path (`generate_review_video`) keeps the same
  behaviour and error messages.
- New `generate_reject_video(reasons, inputs, seed, ...)`: code-planned scenes (`TemplateDirector`,
  0 model calls). Text cards for reasons with no public page. A failed live capture falls back to a
  text card showing the URL. The manifest audit records `model_calls: 0` and the text-card stages.
- The banner caption is label-aware ("not a screenshot of your code" / "not a logo" / "not AI art").
- Exported `generate_reject_video`, `RejectVideoInputs`, `TemplateDirector` from `clanker.review.video`.
- `evals/jev/demo_video.py` now uses the production entry point. Real runs:
  - Cosmic Catcher: 3 scenes, 25 s, 2.0 MB, 36 s;
  - b552fced: banner only, 13 s, 1.0 MB, 17 s.
  Both had 0 model calls and no capture failures.
- `AI/context/v2-architecture-plan.md`: documented the code-only director for first-layer rejections.
- Tests: `tests/test_template_director.py` now also covers the pipeline (fallback card, scene order, no
  "primary" label, rework wording, unmappable reasons). `uv run pytest -q` gives 129 passed. Ruff is clean.

## Open questions / for the human
- Music on or off (currently configurable, on by default); video length.
- The rejection video only gets invoked once the first-layer (Jev) review is wired into `ReviewRunner`,
  which is the next step. The runner currently uses the DeepSeek path, with video disabled via `VIDEO_ENABLED=false`.

## Files touched
- `src/clanker/review/video/{pipeline.py,template_director.py,compositor.py,__init__.py}`,
  `src/clanker/review/reject_message.py`, `tests/test_template_director.py`,
  `evals/jev/demo_video.py`, `AI/context/v2-architecture-plan.md`.
