# Video tooling and benchmark research

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Reviewed the PDF benchmark (`review_report (3).pdf`), the hand-directed
  `ferrocompiler-review.mp4`, and the uncommitted video MVP implementation.
- Extracted an eight-frame contact sheet and inspected the output metadata. The demo is
  H.264/yuv420p at 1280x800, 25 fps, 37.36 seconds, and 1,492,560 bytes.
- Checked current official Playwright and Chrome documentation. Playwright 1.61 has a
  first-class `page.screencast` API (direct video, JPEG frame callbacks, chapters, HTML
  overlays, and action annotations) that the earlier research did not consider.
- Evaluated how to use the PDF as a repeatable benchmark rather than relying solely on
  mutable live GitHub pages.

## Why / decisions made
- The current module is a useful visual prototype, but it is not bulletproof yet: it has
  no tests, total-scene watchdog, URL/SSRF guard, output duration/size validation, or
  stable offline fixture.
- Keep the PDF case as the canonical product benchmark, but split it into a frozen local
  benchmark for CI and a live-GitHub canary. A live page cannot be a deterministic test.
- Prefer an evidence-capture pipeline over recording arbitrary live pages for the final
  renderer: navigate and resolve the target once, save a screenshot plus target rectangle
  and provenance, then compose/record a controlled local scene. This preserves visible
  proof while removing network/page animation/compositor variability from the video pass.
- Before expanding custom canvas code, benchmark Playwright 1.61 `page.screencast` against
  the existing `record_video` path. Its built-in chapters/overlays can replace some custom
  title/callout mechanics, though it does not itself provide a spotlight cutout.
- The 37-second demo is too long and repetitive for the single primary failure in the PDF.
  A benchmark target around 15–22 seconds with one primary evidence scene and at most one
  corroborating scene is more appropriate.

## Files touched
- `AI/journal/2026-07-19-23-video-tooling-benchmark-research.md` — created — records this
  research and recommendation.

## Open questions / for the human
- Whether the preferred product style is a live browser walkthrough or a cleaner
  evidence-snapshot composition; the latter is recommended for reliability.
- Exact maximum video duration and Slack upload-size budget.

## Next steps
- Build a small benchmark harness around the ferrocompiler case with frozen page fixtures,
  a canonical script/evidence manifest, visual checkpoints, ffprobe validation, and failure
  injection.
- Run the same fixture through (a) current `record_video`, (b) Playwright `page.screencast`,
  and (c) controlled snapshot composition, then choose based on measured reliability and
  implementation complexity.
