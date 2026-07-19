# PDF-to-video per-review agent workload estimate

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Compared the ferrocompiler PDF's extracted text with the final director manifest.
- Separated one-time renderer/style development from recurring work for each review.
- Estimated the model calls, agent tool calls, browser operations, tokens, and wall time
  needed when a completed PDF is the only review input.

## Why / decisions made
- For this PDF, all review facts needed for the video are already present: project, author,
  repository URL, verdict, failure explanation, GitHub-search corroboration, and two fixes.
- With the renderer built, the normal director should be one structured completion with no
  browser tools. Deterministic code should extract PDF text, capture the selected URLs,
  locate known evidence or fall back to the viewport, render, encode, and validate.
- This particular case can be compiled without any LLM; a small model is useful only for
  selecting non-redundant scenes and tightening copy.
- The preferred upstream input remains structured `ReviewResult` evidence rather than PDF,
  because PDF parsing discards structure and may omit exact visible anchor text.

## Files touched
- `AI/journal/2026-07-19-25-pdf-to-video-agent-work-estimate.md` — created — records this
  workload analysis.

## Open questions / for the human
- Whether videos should always include corroborating evidence or only the minimum primary
  proof needed to explain the verdict.

## Next steps
- Define the small `PdfVideoBrief` output schema and test whether DeepSeek V4 Flash can
  reliably produce the ferrocompiler manifest in one completion across repeated runs.
