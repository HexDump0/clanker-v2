# First layer: APPROVE vs NEEDS HUMAN

**Date:** 2026-10-01 · **Agent:** Claude Code (Opus 5.5) · **Type:** feature

## What was done
- The human asked for two different non-reject outcomes: **APPROVE** when every check Clanker runs passed,
  and **NEEDS HUMAN** when Clanker is unsure. Before this, every non-reject was "NEEDS HUMAN".
- `rules.reject_decision` still returns REJECT/PASS (the evals depend on it). `FirstLayerReviewer` maps PASS to
  APPROVE or NEEDS_HUMAN via `_unsure_reasons`:
  - near misses (Jev score within 0.2 of its limit; 4–5 modern AI CSS signals);
  - context flags: demo_not_testable ≥ 0.6, not_eligible ≥ 0.5, and feedback_ignored ≥ 0.7 when previously rejected;
  - missing evidence: no demo link, demo not rendered or behind a bot check, banner unclear or unavailable,
    README unverified, code not read (an unsupported host, or files not read), commit history unavailable
    (GitHub/GitLab), project type confidence < 0.5.
  `FirstLayerResult.unsure` holds the reasons. ReviewOutput maps APPROVE → `ReviewVerdict.APPROVE` (green in Slack)
  and NEEDS_HUMAN → `FLAG_FOR_HUMAN`, with the reasons as feedback.
- PDF: a green APPROVE card with "All checks passed"; NEEDS HUMAN has a "Why Clanker isn't sure" list.
- Tests: clean submission → APPROVE; near miss, missing history, unrendered demo and context flags → NEEDS_HUMAN.
  218 pass.

## Measurements
- Eval simulation (margin 0.2): holdout REJECT 98 (11% human-approved), APPROVE 21 (62%), NEEDS HUMAN 67 (28%).
  Dev: APPROVE 15 (60%), NEEDS HUMAN 42 (24%). The base approval rate is 23%. So **about 4 in 10 APPROVEs are still
  human rejects** (mostly AI-use calls). APPROVE must not be read as a rubber stamp.
- Live: 6 pending certs gave 2 APPROVE (ESP32-PNA, CornOS), 3 NEEDS HUMAN, 1 REJECT (banner). Fleeting (GitLab) is NEEDS HUMAN.

## Files touched
- `src/clanker/review/first_layer/{reviewer.py,report.py}`, `src/clanker/templates/first_layer_report.typ`,
  `tests/{test_first_layer.py,test_ai_css.py,test_forges.py}`, `AI/context/v2-architecture-plan.md`.
