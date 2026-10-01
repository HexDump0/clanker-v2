# UI redesign v2 (match the dashboard) + Review PDF in the extension

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** feature

- Human: the UI "still looks like AI slop"; also the review PDF should be visible in the extension.
- Looked at the real dashboard (Playwright with the owner's session, read-only screenshots of the list and a cert page). Findings that
  contradicted my first redesign: the whole site is **Space Grotesk** (not Geist), labels are tiny tracked uppercase, the stats are one
  flat bar with dividers and one amber hero number (not tile cards), filters are outlined buttons with a dot + dim count, lists are dense
  tables, statuses are small tinted text / square badges (not rounded pills), detail pages are breadcrumb + banner + main column + key/value
  info column, buttons are small outlined, almost no icons.
- Rebuilt on that: `ui.css`, `ui.js` (now `parts()` so each surface arranges banner/message/video/reasons/info/feedback; `detail()` stacks
  them for the cert drawer), `page.css`, `judgements.js` (stats bar, filters, sortable table, detail view with prev/next, triage advance),
  `panel.css`, `content.js`. Dropped the Geist fonts. A bug found by screenshot: `inherit` inside `font-family` voids the declaration
  (the page rendered serif); the panel inherits the host page font instead.
- PDF: `GET /api/results/{id}/pdf` (404 if no file/missing), `ClankerApi.pdfBlob`, "Review PDF" button (disabled when none). The video endpoint
  also 404s cleanly when the file is gone. Test added (237 pass).
- Verified with jsdom (list, detail, label → next, PDF open, keyboard) and Playwright screenshots on the dashboard's real HTML.
  Not tested in a real extension install or Firefox.
