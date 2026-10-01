# Fix: Clanker panel only appeared on some cert pages

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** fix

- Symptom: the panel appeared sometimes, not others. Cause: `content.js` was registered for `https://ds.shipwrights.dev/*/certifications/*`,
  and Chrome/Firefox only inject at page *load*. The dashboard is a single-page app, so clicking a ship from the list never reloads and
  the script was never injected (a refresh made it appear). `nav.js` already matched `/*`.
- Fix: one content script entry on `https://ds.shipwrights.dev/*` loading api.js, ui.js, content.js, nav.js; `content.js` already watches the
  URL (now every 400ms). Verified with Playwright: absent on the list page, present after a client-side navigation, gone on going back.
- The user's screenshots showed the pre-redesign UI: the browser was still running the old extension build (needs a reload on
  chrome://extensions / about:debugging after each update).
