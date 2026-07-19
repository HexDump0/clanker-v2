# Existing tooling research for review videos

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Researched current PDF-to-video products, product-demo recorders, managed JSON video
  APIs, open-source code renderers, and Playwright's current Screencast support using
  official documentation and project repositories.
- Compared each category with Clanker's evidence-driven review-video requirements.
- Wrote a dated landscape note with recommended local, self-hosted, and managed stacks.

## Why / decisions made
- No researched turnkey product owns the complete PDF/review-to-live-evidence workflow.
- Playwright remains the right capture layer because Clanker must visit and verify arbitrary
  evidence pages.
- Creatomate is the strongest managed rendering candidate; Revideo is the strongest
  licensing-friendly self-hosted renderer candidate; the current local compositor remains
  reasonable while the template is simple.
- Generic PDF-to-video and product-demo products do not replace the evidence layer.

## Files touched
- `AI/notes/video-tooling-landscape-2026-07-19.md` — created — research findings and
  recommendations.
- `AI/journal/2026-07-19-28-existing-video-tooling-research.md` — created — this entry.

## Open questions / for the human
- Preference between minimal dependencies, a Node-based MIT renderer, or a managed cloud
  template/rendering service.

## Next steps
- If desired, run the ferrocompiler benchmark through Revideo and Creatomate sandbox to
  compare implementation size, visual fidelity, render time, and operational cost.
