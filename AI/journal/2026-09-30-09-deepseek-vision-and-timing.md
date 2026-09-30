# DeepSeek V4.1 Flash for banner + screenshot vision; first-layer timing

**Date:** 2026-09-30 · **Agent:** Claude Code (Opus 5.5) · **Type:** feature

## What was done
- The human said Space Bunny is going away. Switched the banner check to `deepseek/deepseek-v4.1-flash`
  ($0.02/M input, image input, 33 upstream providers), with reasoning off and max_tokens 20. It is configurable
  via `JEV_BANNER_MODEL`. Added `evals/jev/relabel_banners.py`; the old labels are backed up in
  `data/eval/jev/*/evidence2.spacebunny.bak.jsonl`.
- Holdout v2 with DeepSeek banners: 107 rejects at 87% precision, catching 65% of human rejects, with 14/43 good projects bounced.
  banner_bad: 31 fires at 84% (Space Bunny: 20 at 95%). Dev banner precision: 70% (Space Bunny: 64%).
- Switched the production screenshot describer default (`VISION_MODEL_NAME`) from `qwen/qwen3.8-flash`
  to `deepseek/deepseek-v4.1-flash` in `config.py`, `.env.example`, `README.md` and the local `.env`, and
  updated the test. `uv run pytest -q` gives 124 passed.
- Timed 4 real demos: render plus DeepSeek description took 4.8–9.6 s; GitHub evidence plus banner took 3.4–4.4 s in
  parallel. A first-layer review is about 6–11 s including Jev, compared with about 50–55 s p50 for the current DeepSeek agent path.

## Open questions / for the human
- `.env` still has `AI_PROVIDER=hackclub`, but Hack Club AI access is gone. Production needs `openrouter`.
- These changes are not committed yet.

## Files touched
- `src/clanker/config.py`, `tests/test_review.py`, `.env.example`, `README.md`, `.env` (local).
- `evals/jev/evidence2.py`, `evals/jev/relabel_banners.py`.
