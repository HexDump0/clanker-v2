# Extension UI/UX redesign

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** feature

- Human: the UI looked bad; follow the website's design and make it very functional.
- Design source: the dashboard's real CSS (read-only fetch of its public static CSS): graphite theme tokens (surface/edge/ink
  oklch values, accent `#23bbf8`), tinted semantic pills/buttons (`/8-10%` fill, `/25%` border), rounded-lg, Geist + Space Grotesk.
  Fonts bundled in `extension/fonts/` (latin subsets) for the extension page; the panel inherits the page's fonts.
- New shared files: `ui.css` (tokens + components), `ui.js` (hyperscript, icons, `ClankerUI.detail` = the result view used by both
  surfaces), `page.css`, `panel.css`. `judgements.js` and `content.js` rewritten on top of them.
- Judgements page: stats row (judged/rejects/approves/needs human/agreement %), verdict + "to review/wrong/right" filters with counts,
  search, master/detail with selected-row accent, video autoloaded and cached, copy message, right/wrong with reason chips + note,
  re-request, "Review a ship" dialog (link or ID), settings dialog with connection test, export, keyboard shortcuts, loading/empty/error
  states, single-column mobile layout. Labelling a ship in "To review" moves to the next one (triage flow).
- Cert panel: floating button with verdict pill, slide-in drawer (header, summary, reason chips, message with Copy/Use reason,
  video with Use video, feedback, re-request); Esc closes; no-result and error states; hides while the sidebar page is open.
- Backend: results now store `reason_labels` (human text) next to the reason codes; the UI falls back to prettified codes for older records.
- Checked with jsdom (interaction flows) and Playwright/Chromium screenshots against the real dashboard HTML (sidebar, drawer, page).
  Not tested in a real extension install or Firefox. Test scripts were scratch and are not in the repo (no JS test setup).
