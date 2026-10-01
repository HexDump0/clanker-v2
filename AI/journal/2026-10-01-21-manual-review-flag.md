# "Clanker was wrong" = flag for manual review

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** feature

- Human: labels shouldn't just be stored data. "Right" is info only; "wrong" should send the ship to humans and mark the review
  "Clanker got this one wrong, please review manually" for everyone else.
- Backend: `ResultRecord.manual_review` (computed: feedback is "wrong") and `slack_ts` (the thread the review was announced in,
  saved by `service` after announcing; survives re-reviews). `POST .../feedback` accepts `right|wrong|clear`; on the change into "wrong"
  it calls `on_manual_review` once (not on note edits). `service.flag_manual_review` → `Announcer.post_manual_review` posts in the ship's
  thread (top-level if no thread known), with the wrong reasons, the note and the ship-group ping.
- Extension: orange `flag` tone ("Manual review") replaces Clanker's verdict in the badge/status/FAB; banner for other reviewers; Use reason /
  Use video are hidden on flagged ships; wrong reasons are struck through; wrong form says what it does and the button reads
  "Flag for manual review"; "Clear label"; Clanker page gets a Manual review stat and filter.
- Not done / open: who flagged it is not recorded (the API doesn't identify users); in hosted mode the last label wins. Re-requesting a
  review clears the flag only if the verdict/reasons change (existing rule). A flagged ship is not written to the dashboard (no internal note).
- Tests: 242 pass. Checked with jsdom (flag, queue, banner, clear) and Playwright screenshots.
