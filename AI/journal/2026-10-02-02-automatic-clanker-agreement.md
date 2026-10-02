# Automatic "was Clanker right?" from the review log

**Date:** 2026-10-02 · **Agent:** opencode (space-bunny-free) · **Type:** feature

## What was done

- `clanker.results.infer_agreement(record)` derives whether a human reviewer agreed with Clanker,
  and `ResultRecord.auto_agreement` / `.auto_reason` expose it as **computed fields** — never
  stored, so they cannot go stale, and they never touch `feedback`.
- `extension/ui.js`: `autoMeta` / `autoLine` / `autoTag`. The "Was Clanker right?" card gains a
  tinted panel above the buttons ("Clanker was right · Clanker said reject; a reviewer returned
  it by frog · Read off the reviewer's decision. Nobody clicked this."), and the table's Feedback
  column shows `✓ inferred` / `✗ inferred` when nobody has labelled the ship.
- `extension/judgements.js`: the All data tab's **Agreement** stat is now computed from the
  inferred verdicts rather than from the handful of hand-made labels (e.g. "50% · 2 inferred").
- 15 new tests in `tests/test_status.py` (313 pass, ruff clean). Verified in Chromium against
  mocked API responses.

## The rules

| Clanker | reviewer | inferred |
|---|---|---|
| REJECT | returned | right |
| APPROVE | approved | right |
| REJECT | approved | wrong |
| APPROVE | returned | wrong |
| NEEDS HUMAN | anything | **not scored** |

Deliberately not scored:

- **A ship a human already labelled.** Their word wins. `manual_review` is a human-only flag with
  real consequences (takes the ship off the Clanker queue, pings Slack, shows a banner to other
  reviewers), so an *inferred* disagreement must never trigger it — hence `autoMeta` returns null
  whenever `manual_review` is set, and the UI wording for the inferred-wrong case is "A reviewer
  disagreed" rather than "Clanker was wrong".
- **A ship nobody has reviewed yet.**
- **A review older than Clanker's verdict.** This is the trap. Stardance's review log keeps one
  row per ship — its *latest* review. Verified live: 500 rows with 500 distinct ships, and 16 ships
  whose own feedback says "again as mentioned before" / "I can still see some AI usage" still
  appear exactly once. So after a resubmission the logged action belongs to the *previous* attempt,
  and comparing it to a newer Clanker run would score a ship Clanker never saw. The guard is
  `reviewed_at < created_at -> unscored`; unparsable or missing timestamps do not block scoring,
  because a missing timestamp is not proof.
- **NEEDS HUMAN / FLAG_FOR_HUMAN.** Clanker claimed nothing either way, so a human bouncing it is
  not a correction of Clanker. Counting those as disagreement would unfairly penalise the
  needs-human bucket — which is where the queue's real work sits.

A returned-then-resubmitted ship still scores its agreement (the human did send it back, which is
what Clanker asked for) and sits back in the queue, so both facts are visible at once.

## Live check against the 10 stored results

6 of 10 scoreable; 4 agreed, 2 disagreed.

| Clanker | reviewer | | project |
|---|---|---|---|
| REJECT | returned | agree | My first slack bot!, Portfolio Website, REACTOR, Simon says |
| APPROVE | returned | **differ** | Porpholio, Stardance |
| NEEDS HUMAN | returned | — | Complex CSH Tracker, vn_folks |
| — | unreviewed | — | P, Slack Bot with a Humor |

Both disagreements are the same shape: Clanker approved, a human returned it. That is the
AI-code leniency the Jev evals predicted (62% of APPROVEs were human-approved there), and it is
now measurable continuously instead of on a frozen eval set. **Not yet checked**: whether those
two disagreements were humans being right about AI use, or Clanker approving something it should
not have.

## Files touched

- `src/clanker/results.py` — `infer_agreement`, `auto_agreement`, `auto_reason`, `_parse_iso`.
- `extension/{ui.js,judgements.js}`, `extension/ui.css` — inferred-agreement display.
- `tests/test_status.py`, `AI/context/v2-architecture-plan.md`, `README.md`.

## Open questions / for the human

- The review log truncates reviewer feedback at ~120 chars, so the *reason* a human disagreed is
  mostly invisible. Worth chasing only if we want per-reason precision from live data.
- `export_feedback_jsonl` still exports only hand-labelled ships, so the inferred rows do not
  reach `evals/`. They are in the API payload already, so exporting them is a small change.
- Scored pool is only ships whose log entry is newer than Clanker's review, which on a fresh
  install excludes everything Clanker reviewed in the last few minutes. That resolves itself as
  humans get to the queue.

## Next steps

- After a redeploy with the 87 existing results, watch the All data tab's Agreement figure and
  compare it with the eval's 89% reject precision.
- Consider whether an inferred "wrong" on an APPROVE should ever escalate (e.g. tighten the
  AI-code thresholds). Deliberately not automated.
