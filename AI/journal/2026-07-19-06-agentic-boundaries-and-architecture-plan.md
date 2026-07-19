# Documented agentic boundaries and v2 architecture plan

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** decision

## What was done
- Wrote the human-requested v2 architecture plan: workflow, contracts, isolated
  artifacts, Slack routing, provider compatibility, delivery phases, and safety.
- Explicitly separated agentic judgment/planning from deterministic orchestration.
- Marked the plan as human-requested so it is not confused with the scrapped inferred
  roadmap, and listed it in `AI/README.md`.

## Why / decisions made
- The review agent owns investigative judgment. A narrow video planner may arrange
  existing evidence; browser recording normally follows a deterministic plan.
- Application code orchestrates the workflow; agents do not spawn other agents.
- Browser recovery may become narrowly agentic only after deterministic recording works.
- `ReviewResult` is canonical; PDF and video are independently retryable artifacts.

## Files touched
- `AI/context/v2-architecture-plan.md` — created — authoritative requested plan.
- `AI/README.md` — modified — lists the new context document.
- `AI/journal/2026-07-19-06-agentic-boundaries-and-architecture-plan.md` — created.

## Open questions / for the human
- The five decisions at the end of the architecture plan remain open.

## Next steps
- Human reviews the plan and adjusts its open decisions before implementation.
