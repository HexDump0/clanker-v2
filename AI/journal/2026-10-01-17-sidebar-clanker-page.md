# "Clanker" page in the dashboard sidebar

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** feature

- Human wanted the judgements page inside the dashboard, as a sidebar entry like "My Stats" / "My Balance".
- Dashboard facts (read from the SSR HTML, no mutations): sidebar is `aside nav.space-y-0.5` of plain `<a>` links; content panel is
  `<main class="… flex-1 p-8">`; inactive links have `border-transparent`.
- `extension/nav.js` (all `ds.shipwrights.dev/*` pages): clones an inactive link (same styling/collapse behaviour; cloneNode drops
  React handlers, so the app ignores it), swaps icon/label, appends it; a MutationObserver re-adds it after SPA re-renders.
  Click toggles a fixed overlay sized to `<main>` holding an iframe of `judgements.html?embedded=1`.
  No route is added to the app (a reload of a fake `/clanker` URL would 404), so there is no URL for the page.
- Manifest: added the content script and `web_accessible_resources` (judgements.html/js, api.js).
- Verified with jsdom against the real sidebar HTML: link added, overlay opens, other link/toggle closes it. Not tried in a real
  browser: active-state styling is a guess (inline blue left border), overlay alignment while the sidebar expands.
