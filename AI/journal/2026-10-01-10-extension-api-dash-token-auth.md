# Extension API auth: validate the caller's Dashboard token

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** decision

## What was done
- Human decisions: extension must work on Chrome and Firefox; runs locally first, then hosted on the internet; auth is the
  user's Dashboard session token, which we only *validate* (never use) to confirm they have Dashboard access; commit periodically.
- Replaced the static `EXTENSION_API_TOKEN` with `EXTENSION_API_ENABLED` / `EXTENSION_API_HOST` (default 127.0.0.1).
- `clanker.api.dashboard_validator`: one read-only `get_workplace()` call with the caller's token. 401/403 means rejected.
  Valid tokens are cached by SHA-256 for 5 minutes; failures are never cached. Tests inject a fake validator.

## Open questions / for the human
- **Hosted mode and video upload:** `POST /results/{id}/upload-video` uses the *server's* configured session. Hosted, that would
  attach videos as the server owner, not the user. Proposed fix: the extension downloads the video from the API and does the
  3-step upload itself from the dashboard page with the user's own cookies, so the server never uses a user's token. Not done yet.
- Hosting needs TLS (reverse proxy) and a CORS origin policy; CORS is currently `*`, fine because auth is a bearer token.

## Files touched
- `src/clanker/{api.py,config.py,service.py}`, `.env.example`, `tests/test_extension_api.py`. 225 tests pass.
