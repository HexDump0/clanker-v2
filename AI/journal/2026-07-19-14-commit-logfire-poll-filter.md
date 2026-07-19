# Commit Logfire poll filter

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** fix

## What was done
- Reviewed and prepared a focused commit containing the watcher-poll Logfire exclusion,
  its regression tests, and the associated implementation journal.
- Confirmed no unrelated changes were present in the worktree.

## Why / decisions made
- Keeping this observability change isolated makes it straightforward to review or
  revert without affecting the earlier review-delivery fixes.

## Files touched
- `AI/journal/2026-07-19-14-commit-logfire-poll-filter.md` — created — records the
  requested commit operation.

## Open questions / for the human
- None.

## Next steps
- Restart the bot so HTTPX instrumentation loads the exclusion.
