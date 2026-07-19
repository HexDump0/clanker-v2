# Clarify current video renderer reuse boundary

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** decision

## What was done
- Clarified that the ferrocompiler benchmark proves a reusable rendering approach but is
  not yet a universal PDF-to-video implementation.
- Identified which parts are already generic and which remain benchmark/GitHub-specific.

## Why / decisions made
- Avoid describing prototype development as finished one-time infrastructure.
- The correct next milestone is a generic renderer consuming a validated video manifest;
  PDF parsing/planning should be a separate adapter.

## Files touched
- `AI/journal/2026-07-19-26-video-renderer-reuse-clarification.md` — created — records this
  clarification.

## Open questions / for the human
- Whether the next implementation should support all evidence types immediately or begin
  with GitHub repository accessibility, README, and file/line evidence.

## Next steps
- Refactor the benchmark script into generic capture, composition, and encoding modules;
  remove ferrocompiler-specific defaults and add a PDF-to-manifest adapter.
