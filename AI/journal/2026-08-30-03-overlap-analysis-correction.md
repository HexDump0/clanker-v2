# Correct the overlap analysis — reconcile verified working

**Date:** 2026-08-30 · **Agent:** opencode (GLM) · **Type:** fix (analysis correction)

## What was done
- Re-examined the "0 overlap between Stardance and the Dashboard" conclusion from
  journal 2026-08-30-02 after the owner flagged it as unexpected.
- Root cause of the wrong conclusion: the ad-hoc analysis script compared Dashboard
  `external_id` **strings** against Stardance ship ids parsed as **ints** — the set
  intersection was empty for a type reason, not a data reason. The watcher code itself
  compares str:str and was never affected.
- Corrected picture (verified live, both sides walked fully):
  - Dashboard PENDING: 42 certs; **42/42 are pending on Stardance** (perfect overlap).
  - Stardance PENDING: 108 ships; **66 newest (≈ ship 11026-11080) are missing from the
    Dashboard** — this is the broken/lagging import, and it is one-directional.
  - Dashboard's newest pending external_id is 11025; Stardance page 1 (newest 25) sits
    entirely inside the missing range, which is why the earlier live watcher smoke
    legitimately reconciled 0/25 — correct behavior, not a bug.
- End-to-end reconcile re-run: fed all 108 Stardance ships to
  `StardancePendingSource.resolve` → 42 matched Dashboard certs (e.g. 11025 →
  'StudyBuddy'), 66 held in the awaiting-import retry set.
- Also noted while probing: Stardance's `approved`/`returned` filters behave oddly when
  walked page-by-page (125 unique ids across pages vs a 108 "In queue" metric); the
  watcher only uses `status=pending`, where walked count == metric == 108, so this does
  not affect it. The `In queue` metric reflects the pending count, not the filtered page
  total for other statuses.

## Why / decisions made
- No code changes were needed; the failure was in the analysis script, not the watcher.
- The owner's suggested `sort=date:desc` Dashboard param was checked: it works, but the
  reconcile walks all PENDING pages anyway, so result sets are identical.

## Files touched
- `AI/journal/2026-08-30-03-overlap-analysis-correction.md` — created — this record.
- `AI/context/API.md` — modified — appended verified overlap figures and the
  approved/returned filter caveat to the Stardance admin queue section.

## Open questions / for the human
- None. Watch: when the Dashboard import recovers, the 66 awaiting ships will emit in
  one burst (bounded by the review semaphore); `RESOLVE_MAX_AGE = 6h` may drop them if
  the outage outlasts it.

## Verification
- Live set comparison with consistent types (42/42 overlap).
- Live full-queue reconcile through the real `StardancePendingSource` (42 matched,
  66 awaiting). Read-only throughout.
