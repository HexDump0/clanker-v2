# Re-audited current code against the architecture plan

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Repeated the architecture-plan audit from the current clean commit state rather than
  relying on journal 15's snapshot.
- Reviewed commits and journals added since the first audit, including packet enrichment,
  browser rendering/vision description, guideline changes, and Exa web search.
- Inspected the current service, watcher, result models, runner, packet builder, browser,
  vision, dependencies, deployment, and tests.
- Verified 38 tests pass, Ruff is clean, and `git diff --check` passes.

## Why / decisions made
- The previous audit is now outdated about browser groundwork: Playwright Chromium,
  one-shot page rendering, screenshots, and a factual vision describer are implemented.
  These improve review evidence and are reusable by a future video worker.
- This is not yet the planned video pipeline: there is no `VideoPlan`, recording,
  annotation scene executor, video artifact, isolated worker process/container, retry,
  or Slack video publisher.
- The vision describer is an LLM component but not meaningfully agentic: it receives one
  screenshot and returns a description without selecting actions or tools. The formal
  reviewer remains the primary agentic component; web search and browser-render tools
  expand its available evidence.
- Core structural gaps from journal 15 remain: no durable `ReviewJob`, persisted
  `ReviewResult`, structured `Evidence`, `Artifact` state, resumable stage machine,
  direct Slack command route, independent PDF job, or lifecycle event system.
- The watcher still persists new cert IDs as seen before an in-memory review task has
  completed or been durably accepted, so a crash can lose work.
- Updated approximate assessment: 85-90% of the pre-video happy-path functionality and
  40-45% of the full durability/isolation architecture are present.
- Browser security only partially matches the plan: fresh contexts, no cookies, refused
  downloads, and timeouts exist, but rendering still runs from the main service and URL
  validation does not block private/local network targets or redirects.

## Files touched
- `AI/journal/2026-07-19-21-plan-correspondence-reaudit.md` — created — records the
  updated audit.

## Open questions / for the human
- Whether durable workflow work should precede turning the new browser renderer into a
  recorder.

## Next steps
- Recommended order remains: durable jobs/results/artifacts, independent PDF and direct
  Slack command routing, then reuse the renderer inside an isolated video worker.
