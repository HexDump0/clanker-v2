# Video music off by default

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** fix

- `VIDEO_MUSIC_ENABLED` already existed (default true). Default is now `false`; documented in `.env.example`; test added.
- A `.env` that sets `VIDEO_MUSIC_ENABLED=true` explicitly still gets music (the owner's `.env` does; left untouched).
- Files: `src/clanker/config.py`, `.env.example`, `tests/test_config.py`.

## Correction
- Commit `9c9c892` accidentally emptied `.env.example` (a stray truncating write in an edit script). Restored from `cf4895a`
  plus the music entry. Nothing else was affected; `.env` was never touched by that script.
