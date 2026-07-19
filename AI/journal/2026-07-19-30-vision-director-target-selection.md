# Vision director for screenshot target selection

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** decision

## What was done
- Refined the video architecture around the human's screenshot-first vision-director idea.
- Split ownership among the review agent, deterministic capture worker, and vision director.
- Chose candidate element IDs or normalized image regions as director output instead of
  raw model-authored text or CSS selectors.

## Why / decisions made
- The review agent knows the semantic evidence and provenance, but may have observed it via
  an API rather than the rendered DOM; it should not claim a page-text locator it never saw.
- A vision model can judge what is visually persuasive from screenshots, but OCR text may
  differ from DOM text and is too brittle as a direct programmatic locator.
- Capture code can enumerate visible DOM/accessibility elements with stable per-capture IDs
  and exact rectangles. The vision director selects an ID; code verifies it exists.
- Canvas/image-only evidence can use a normalized rectangle fallback, validated against the
  screenshot bounds.
- One multimodal completion can receive several pre-captured evidence screenshots, choose
  the non-redundant scenes, select highlight targets, and write copy without browser tools.

## Files touched
- `AI/journal/2026-07-19-30-vision-director-target-selection.md` — created — records this
  architecture refinement.

## Open questions / for the human
- Whether the vision director should see clean screenshots plus a separate candidate list,
  or annotated screenshots with candidate-number overlays; the latter is likely easier for
  a small vision model and should be benchmarked.

## Next steps
- Prototype DOM candidate extraction and annotated screenshot generation on the existing
  ferrocompiler benchmark, then test repeated target selection with the intended vision
  model.
