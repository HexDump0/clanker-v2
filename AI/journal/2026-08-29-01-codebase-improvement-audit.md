# Audit codebase improvement opportunities

**Date:** 2026-08-29 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Read the agent conventions, all stable context, the current human-requested architecture
  plan, and the latest journal entries.
- Inspected v2 source, prompts, tests, configuration, dependency graph, Dockerfile, and
  working-tree state without changing application code or user-owned untracked files.
- Ran the lock check, Ruff, pytest, dependency freshness check, and a PyPA `pip-audit`.
- Researched current primary guidance from Playwright, OWASP, Python, Pydantic AI,
  Logfire, Slack, Docker, and OSV.
- Wrote a prioritized audit covering Docker context secrets, browser isolation, SSRF,
  durable/idempotent jobs, prompt injection, authorization/spend controls, telemetry
  privacy, Slack escaping, result contracts, CI/tests, dependencies, evals, and container
  supply-chain hardening.

## Why / decisions made
- No application fixes were made because the request was exploratory and several changes
  require owner choices about Slack authorization, telemetry retention, browser rollout,
  and durable-state scope.
- Recommendations follow the existing human-authored architecture rather than inventing
  a new roadmap. SQLite remains the suggested first durable store; external workflow
  engines are documented as later alternatives, not requirements.
- User-owned untracked benchmark scripts/data were preserved. Their lint issue is
  reported separately from the tracked-source lint failure.
- The Context7 skill was selected for current library guidance, but its connector was not
  available; official upstream documentation and primary advisory sources were used as
  the fallback.

## Files touched
- `AI/notes/codebase-improvement-audit-2026-08-29.md` — created — durable, sourced audit
  and prioritized recommendations.
- `AI/journal/2026-08-29-01-codebase-improvement-audit.md` — created — mandatory session
  record.

## Open questions / for the human
- Which Slack channels/users may invoke chat and paid reviews?
- May production telemetry contain full submission/Slack content?
- Is SQLite acceptable for initial durable workflow state?
- Should browser/video remain enabled until isolation and SSRF controls are complete?
- What quality/cost thresholds should gate prompt or model releases?

## Next steps
- Start with the same-day safety/quality slice in the audit, then implement the durable
  workflow and browser isolation as independently testable units after owner decisions.
