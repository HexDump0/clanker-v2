# No-LLM rejection video prototype

**Date:** 2026-09-30 · **Agent:** Claude Code (Opus 5.5) · **Type:** feature

## What was done
- `src/clanker/review/video/template_director.py`: a code-only director implementing the existing
  `Director` protocol, with zero model calls. It maps first-layer reject reasons to at most 3 scenes, most
  blocking first:
  - live pages: GitHub file at the submission commit (a telltale AI line is highlighted), README
    (heading highlighted), demo/releases/repo pages, and the banner image;
  - text cards for reasons with no public page (raw README link, missing banner, untitled).
  Captions use the same casual Shipwright voice as the reject message.
- `compositor.py`: the "primary" role label is hidden (it read as machine-y), and the URL strip is hidden on text cards.
- `evals/jev/demo_video.py`: renders a video for one real holdout reject.
- Demo: Cosmic Catcher (humans also rejected it). Scenes: raw-link card, style.css with its
  `/* ===== */` banner highlighted, and the AI-style README with its heading highlighted. Output is 25 s,
  1280×720 H.264, 1.7 MB, with 0 model calls. Took 7.4 s to capture and 28.4 s to render and encode (about 36 s total).
- `uv run pytest -q` gives 124 passed. Ruff is clean.

## Open questions / for the human
- Keep the music or go silent? Keep 25 s (intro + 3 × ~5 s + outro), or make it shorter?
- Not yet wired into production and not committed.
