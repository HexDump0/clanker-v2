# Fix: extension "Failed to fetch" on Chrome (Private Network Access)

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** fix

## What happened
- The panel showed "Failed to fetch" on Chrome while the API was running. The content script runs in the https dashboard
  page and calls `http://127.0.0.1:8765`; Chrome sends a Private Network Access preflight and blocks the request unless the
  response has `Access-Control-Allow-Private-Network: true`. Confirmed with curl: the header was missing.
- Fix: added the header to the API's CORS headers (`src/clanker/api.py`) + test. Needs an API restart. Not an issue once hosted publicly.
- Not verified in Chrome itself. Fallback if it persists: route the fetches through the background worker (it has host permissions).
