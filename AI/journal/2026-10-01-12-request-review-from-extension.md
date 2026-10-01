# Request / re-request a Clanker review from the extension

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** feature

## What was done
- API: `POST /api/results/{id}/review` (202, runs `ReviewRunner.review_cert` in the background; saves the result) and
  `GET /api/results/{id}/review-status` (idle/running/failed + error). `ReviewJobs`: one job per cert, shared concurrency limit
  (`MAX_CONCURRENT_REVIEWS`), 60s cooldown (429) because the hosted API is open to any validated dashboard user and reviews cost money.
- Not posted to Slack: extension-requested reviews only update the stored result.
- Extension: panel shows "Request Clanker review" for ships with no result (it used to hide), "Re-request" on judged ones;
  judgements page has a per-card "Re-request review". Both poll until done, then refresh.
- A re-review keeps the human right/wrong label only if verdict and reasons are unchanged.
- Tests: 227 pass (single run, cooldown, failure reporting, disabled without a runner).

## Open questions
- Should any dashboard user be able to spend review budget when hosted? Maybe restrict by role or a daily cap.
- Requests are in-memory only: a restart forgets running jobs/cooldowns.
