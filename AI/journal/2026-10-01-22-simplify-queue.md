# Simplify: one Clanker queue; wrong leaves it, right changes nothing

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** fix

- Human clarified (entry 21 was over-built): no separate "to review / manual review / marked right" queues. One queue; **right** =
  feedback only, stays in the queue; **wrong** = taken off the Clanker queue and marked "Clanker got it wrong" for others.
- UI: removed the second filter row and the To review / Manual review stat tiles. Stats: In queue, Rejects, Approves, Needs human,
  Got it wrong, Agreement. Filters: Clanker queue, Reject, Approve, Needs human, plus one "Clanker got it wrong" filter. The queue =
  everything except `manual_review` ships. Badge/status text is "Clanker got it wrong". Labelling right no longer auto-advances.
- Backend unchanged (`manual_review` = feedback is "wrong"; Slack flag once on the change into wrong).
- Checked with jsdom + Playwright screenshots. 242 Python tests pass.
