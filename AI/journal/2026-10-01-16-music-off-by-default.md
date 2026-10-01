# Video music off by default

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** fix

- `VIDEO_MUSIC_ENABLED` already existed (default true). Default is now `false`; documented in `.env.example`; test added.
- A `.env` that sets `VIDEO_MUSIC_ENABLED=true` explicitly still gets music (the owner's `.env` does; left untouched).
- Files: `src/clanker/config.py`, `.env.example`, `tests/test_config.py`.
