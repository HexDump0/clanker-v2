# Model and provider inventory

**Date:** 2026-08-30 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Read the AI folder conventions, architecture/context files, recent journal entries,
  and the prior provider-compatibility and latency research.
- Traced every current v2 model construction site and inspected only allowlisted,
  non-secret AI settings from the gitignored `.env`.
- Checked the live, unauthenticated Hack Club AI model catalog for the configured model
  IDs and researched current Hack Club AI and OpenRouter documentation.
- Wrote a workload-by-workload model/provider inventory and initial speed implications.

## Why / decisions made
- Distinguished the effective Hack Club AI gateway from the dormant direct-OpenRouter
  provider pins. With `AI_PROVIDER=hackclub`, the application does not send its Alibaba
  or Nex AGI provider restrictions.
- Made no provider or model change: this unit establishes the current baseline before
  benchmarking or optimization.
- Identified the Thinking vision describer and full-size daily praise model as obvious
  benchmark candidates, while preserving formal review quality until measured.

## Files touched
- `AI/notes/model-provider-inventory-2026-08-30.md` — created — detailed researched
  inventory, routing caveat, sources, and speed follow-ups.
- `AI/journal/2026-08-30-06-model-provider-inventory.md` — created — records this work.

## Open questions / for the human
- Is Hack Club AI required for the production deployment, or may the review pipeline use
  direct OpenRouter for deterministic provider routing and performance controls?
- Which matters most for optimization: review wall time, first-token latency, cost, or a
  quality floor? These lead to different model/provider choices.

## Next steps
- Measure one representative review and the two vision workloads end-to-end, including
  rounds, input/output tokens, time to first token, total time, failures, and actual
  upstream metadata where exposed.
- Build a small same-prompt model/provider benchmark only after agreeing on the primary
  optimization target and acceptable quality checks.
