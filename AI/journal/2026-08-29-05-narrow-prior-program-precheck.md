# Narrow prior-program pre-check to explicit disclosures

**Date:** 2026-08-29 · **Agent:** Codex (GPT-5) · **Type:** fix

## What was done
- Replaced the broad "prior-program screening" pre-check wording with an explicit-
  disclosure handoff to `pre_event_commits`.
- Made the prompt directly forbid attempts to discover undisclosed prior submissions.

## Why / decisions made
- Clanker can read declarations and repository dates but cannot reliably discover
  outside competition/YSWS submissions or verify dated Hackatime sessions.
- The eligibility rule remains in check 4, where disclosed but unverified tracked-time
  evidence is escalated to a human.

## Files touched
- `src/clanker/prompts/precheck.md` — modified — accurately scope Clanker's capability.
- `AI/journal/2026-08-29-05-narrow-prior-program-precheck.md` — created — this record.

## Open questions / for the human
- None.

## Next steps
- None.
