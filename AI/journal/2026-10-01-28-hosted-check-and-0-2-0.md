# Hosted server check + extension 0.2.0 build

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** research

- Checked https://clanker.hexdump0.pw (Coolify, behind Cloudflare): `/healthz` 200 with a valid cert, 401 without a token, CORS preflight
  correct (incl. Private-Network header), and with the owner's dashboard token (read-only) `/api/me` returned the identity ("Floppy") and
  10 reviews left. `/api/results` returned 0 results, so after the watcher-state reset the hosted bot had not reviewed the old queue.
- The owner's machine's system resolver did not resolve the new name yet (1.1.1.1 did): stale negative DNS cache. Flush or wait.
- Extension: manifest description rewritten plainly ("Clanker's reviews inside the Shipwrights dashboard."), toolbar title "Clanker",
  version 0.2.0. Built with `API_URL=https://clanker.hexdump0.pw` -> `dist/clanker-chrome.zip` (+ `.xpi`, unsigned). Lint 0 errors.
