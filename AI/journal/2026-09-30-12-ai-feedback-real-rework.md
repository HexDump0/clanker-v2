# AI feedback asks for real rework, not cosmetic fixes

**Date:** 2026-09-30 · **Agent:** Claude Code (Opus 5.5) · **Type:** fix

## What was done
- Per the human: rejection feedback must not imply that removing AI "tells" (emoji, comment banners) is
  enough. Shippers should actually redo the work.
- Video: AI-code and AI-README scenes no longer highlight anything (the telltale-line helper was removed).
  The captions now say small edits or editing the AI text won't be enough: redo the design and code
  yourself and build your own features; write the README from scratch. The outro fixes were reworded to match.
- Message: the ai_code and ai_readme phrasings now carry the same "not just small edits / from scratch" wording.
- Added `tests/test_template_director.py` (AI scenes have no highlight and use rework wording; scene
  order/merge/cap; messages never suggest removing emoji or comments). `uv run pytest -q` gives 127 passed. Ruff is clean.
- Re-rendered the Cosmic Catcher demo (25 s, 0 model calls, 36 s end to end).

## Files touched
- `src/clanker/review/video/template_director.py`, `src/clanker/review/reject_message.py`,
  `tests/test_template_director.py`.
