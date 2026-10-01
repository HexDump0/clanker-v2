# Slack updates for extension-requested reviews

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** feature

- Reverses the earlier "extension reviews don't post to Slack" choice (entry 12) at the human's request.
- `Announcer.announce_review_request(cert, rereview=)`: one embed, **no group ping** (so re-requests don't re-notify everyone)
  plus a thread note ("Review requested" / "Re-review requested from the browser extension"). The outcome (verdict, reject
  message, PDF, video) goes in that thread via the usual `post_outcome`; a failed review posts `post_failure`.
- `service.review_for_extension` wraps the runner for the extension API. Re-request = a result already exists in the store.
  Slack failures are logged and never block the review.
- Not recorded: who asked (the API only validates the token, it does not identify the person). Could be added by reading the
  dashboard's "me" info during validation, if wanted.
- Tests: 234 pass (`tests/test_extension_slack.py`).
