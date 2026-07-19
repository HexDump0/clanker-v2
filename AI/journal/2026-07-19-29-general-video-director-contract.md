# General video director contract and hardening boundary

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** decision

## What was done
- Defined how to generalize and harden the existing snapshot-first video workflow.
- Defined the director as a single structured completion that selects and words scenes but
  cannot browse, invent URLs, choose selectors, control visual design, or render video.
- Proposed separate validated contracts for editorial `VideoBrief` and deterministic
  `CapturedScene` output.

## Why / decisions made
- Keep DeepSeek V4 Flash inside a small, reliable task: ranking supported findings,
  removing redundancy, identifying primary/corroborating evidence, and tightening copy.
- Resolve every URL and evidence target from the canonical review result rather than
  trusting model-generated navigation instructions.
- Keep screenshot capture and final composition separate so arbitrary external pages never
  control the recorded overlay or final layout.
- Begin without an agentic locator-recovery loop; deterministic fallbacks and scene skipping
  are safer and cheaper.

## Files touched
- `AI/journal/2026-07-19-29-general-video-director-contract.md` — created — records this
  design decision.

## Open questions / for the human
- Final maximum scene count and duration; proposed defaults are three evidence scenes and
  25 seconds.

## Next steps
- Add the contracts, generic capture worker, provider adapters, local fixtures, renderer
  refactor, and one-call director in that order.
