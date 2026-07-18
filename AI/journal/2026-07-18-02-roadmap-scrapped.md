# v2 roadmap scrapped (it was agent-inferred)

**Date:** 2026-07-18 · **Agent:** opencode (kimi-k3) · **Type:** decision

## What was done
- Deleted `AI/context/v2-roadmap.md` at the human's request ("scrap the v2 roadmap").
- Removed all references to it from `AGENTS.md`, `AI/README.md`, and
  `AI/context/v1-pain-points.md`.

## Why / decisions made
- The roadmap was **inferred by an agent** (see `2026-07-18-01`), not given by the human:
  its targets (ds.shipwrights.dev direct integration, human-approval gate, milestones
  M0–M4, approval-mode suggestions) were extrapolated from v1 pain points and the mere
  presence of `API.md` in the folder. The human chose to discard it.
- **Decision recorded:** v2 goals/requirements come from the human only. Agents must not
  invent or resurrect a roadmap from v1 pain points. Pain points are observations, not
  requirements.
- `v1-pain-points.md` was reworded so it reads as neutral observations, not a plan.

## Files touched
- `AI/context/v2-roadmap.md` — deleted — human scrapped it
- `AGENTS.md` — modified — roadmap reference replaced with a "no roadmap; ask the human" note
- `AI/README.md` — modified — structure diagram updated
- `AI/context/v1-pain-points.md` — modified — header reworded (observations, not a plan)
- `AI/journal/2026-07-18-02-roadmap-scrapped.md` — created (this file)

## Open questions / for the human
- What should v2 actually be? Share your own improvement list/vision when ready and it
  will be recorded as the authoritative direction.

## Next steps
- Wait for human direction before writing any v2 code or plans.
