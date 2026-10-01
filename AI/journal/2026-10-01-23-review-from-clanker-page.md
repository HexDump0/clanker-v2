# Review (reject) directly from the Clanker page

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** feature

- Human asked for this explicitly, including that it *actually rejects* through the real dashboard flow with the reviewer's own account,
  locally in the browser, never on the server (multiple reviewers will use it). That is the explicit sign-off AGENTS.md requires for the
  `[MUTATING]` claim/upload/review endpoints. The Clanker server still never calls them.
- Flow (confirmed against the dashboard's own JS and a live cert detail's field names): `GET cert` → `POST claim {unclaim:false}` (if not
  IN_REVIEW) → optional 3-step video upload → `POST review {verdict:"REJECTED", comment}`. Refuses if APPROVED/REJECTED, or IN_REVIEW and
  claimed by someone else (unless viewerIsGlobalAdmin); skips the claim if already the claimer. If a step after claiming fails, the error
  says the ship is now claimed by the user.
- Why a bridge: the Clanker page is an extension iframe, and cookie behaviour for cross-site extension fetches differs across browsers.
  So `bridge.js` (iframe) → `postMessage` → `nav.js` (on the dashboard page) → `dash.js` (same-origin fetch with the user's cookie). nav.js
  accepts messages only from the iframe it created, from that iframe's origin, whitelists ops (`status`, `reject`) and validates ids.
  `dash.js` also replaces the upload code that was in `content.js`.
- UI: Feedback card (editable textarea autofilled with Clanker's message, Reset/Copy, char count, drafts kept per ship), Review card
  (dashboard status, "Attach Clanker's video", **Reject the project** with a confirm dialog that previews the text), then the right/wrong
  card directly below. Ships marked wrong are not prefilled.
- Verified end to end in Chromium (route-mocked dashboard, real extension scripts, real iframe + postMessage): the request sequence and bodies
  above, edited text submitted, and the guards (claimed by another, already decided, already mine). Not run against the real dashboard.
- Not done: no Approve button (not asked for); rejecting does not auto-label Clanker right; no undo after submitting.
