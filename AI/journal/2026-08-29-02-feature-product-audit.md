# Reframed the improvement audit around product features

**Date:** 2026-08-29 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Re-reviewed the current watcher, review pipeline, structured output, Slack delivery,
  dashboard client, API reference, recent architecture journals, and the uncommitted
  historical benchmark work from a product/feature perspective.
- Ran the local benchmark scorer against `data/bench/results.jsonl` and used its measured
  agreement, error categories, latency, and manual adjudication as prioritization evidence.
- Researched current official Shipwrights behavior/rules, Slack interaction surfaces,
  Playwright evidence tooling, GitHub AI-review UX, GitHub commit comparison, CodeRabbit
  incremental reviews/learnings, and Pydantic Evals datasets.
- Wrote a feature-focused audit with a ranked backlog and suggested build order.

## Why / decisions made
- The previous audit over-indexed on hardening after the human wanted feature ideas, so this
  unit deliberately excludes security as a roadmap driver.
- The core review engine is already feature-rich; the largest product gap is the reviewer
  workflow around it. An interactive Slack cockpit, revision-aware re-reviews, functional
  test packs, and a correction/eval loop were ranked ahead of additional report polish.
- The benchmark's human labels are inconsistent: 14 of 15 apparent bot false rejects were
  manually judged to be human errors. Recommendations therefore use raw agreement as a
  directional signal and call for adjudicated feedback rather than treating it as truth.
- Web Apps were chosen as the first functional adapter because they represent 310 of 433
  scored benchmark records and the repo already contains a Playwright-based renderer.
- Submitter preflight is recommended only after deterministic checks and reviewer feedback
  have been validated, and it should never present itself as an official verdict.
- Dashboard mutations remain human-confirmed product actions, not autonomous behavior.

## Files touched
- `AI/notes/feature-product-audit-2026-08-29.md` — created — detailed feature analysis,
  research references, priorities, and build order.
- `AI/journal/2026-08-29-02-feature-product-audit.md` — created — this session record.

## Open questions / for the human
- Whether the first target user is the Shipwright reviewer or the submitter.
- Whether a confirmed Slack action may eventually claim and submit a dashboard review.
- Which project type should receive the second functional test pack after Web Apps.
- Whether review video is a requirement or an optional artifact whose usage should decide
  future investment.

## Next steps
- Human chooses one product slice. The recommended first slice is persisted review records
  plus an inline Slack result card with per-finding feedback; it creates the foundation and
  feedback data needed by nearly every later feature.
