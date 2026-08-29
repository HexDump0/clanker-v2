# Clarify prior-program screening capability

**Date:** 2026-08-29 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Traced the newly added prior-program prompt rule through the pre-check, rubric,
  verdict logic, submission packet, and dashboard models.
- Confirmed what Clanker can and cannot establish from its current evidence.
- Made no application or prompt changes in this unit; prepared a capability explanation
  for the owner.

## Why / decisions made
- The rule came from the supplied guidelines covering projects submitted to another
  competition/game jam/hackathon and projects predating Stardance or another YSWS.
- Clanker can reliably inspect commit dates and the dashboard's `updated_project` field,
  and can notice explicit disclosures in descriptions, READMEs, devlogs, or prior
  reviews.
- Clanker cannot reliably discover undisclosed participation in outside programs and
  does not receive dated Hackatime sessions, so it cannot independently prove that time
  was tracked after Stardance began. The current prompt therefore forbids inference and
  escalates ambiguous disclosed cases to a human.
- The pre-check item is a routing flag, not an instant rejection or a new structured
  output field.

## Files touched
- `AI/journal/2026-08-29-04-prior-program-capability-clarification.md` — created — this
  mandatory session record.

## Open questions / for the human
- Whether to keep the pre-check routing flag, move the rule entirely into check 4 for
  simpler wording, or add dated Hackatime evidence to the packet later.

## Next steps
- If the owner wants fully deterministic enforcement, expose program history and dated
  tracked-time evidence through the dashboard API/packet rather than asking the model to
  infer it.
