# Narrow scope to agent tools, not queue behavior

**Date:** 2026-08-29 · **Agent:** Codex (GPT-5) · **Type:** decision

## What was done
- Revised the HAR audit recommendations after the owner clarified the desired product
  boundary.
- Removed queue sorting, returned-cert watching, and revision-aware queue state from the
  proposed work.
- Reframed Dashboard queue totals, wait times, oldest-cert information, and type counts as
  read-only chat context only.

## Why / decisions made
- The watcher should remain intentionally narrow: detect the latest new pending project
  and start its review. It should not become a queue manager or automatically process
  returned certifications.
- Current improvement work should focus on the evidence and informational tools available
  to the review/chat agents.
- Attempt history still matters as certification-detail evidence supplied to a review; it
  is not watcher state or a reason to expand watcher behavior.

## Files touched
- `AI/journal/2026-08-29-10-tool-first-scope-clarification.md` — created — mandatory record
  of the owner's scope decision.

## Open questions / for the human
- None required before planning; implementation details can be selected tool by tool.

## Next steps
- Restore read-only Dashboard access, enrich certification and Stardance evidence tools,
  and optionally add a small queue-statistics tool registered only with the chat agent.
