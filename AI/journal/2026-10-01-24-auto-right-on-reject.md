# Auto-label "Clanker was right" when a reviewer rejects

**Date:** 2026-10-01 · **Agent:** Claude Code (Sonnet 5.5) · **Type:** feature

- Human asked that rejecting from the Clanker page also marks Clanker right (entry 23 had left it out).
- Rule: only when Clanker's verdict was REJECT (a human reject then agrees with it) and the ship has no label yet. Approve / needs-human
  verdicts followed by a human reject are not treated as agreement, and an existing label is never overwritten. A failure to save the
  label is ignored (the dashboard rejection already succeeded); the toast says "Rejected X and marked Clanker right" when it saved.
- `extension/judgements.js` only. Verified in the Chromium E2E: the dashboard review POST followed by `feedback {"agreement":"right"}`.
