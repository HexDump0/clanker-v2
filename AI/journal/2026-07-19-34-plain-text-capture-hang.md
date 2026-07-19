# Fix plain-text evidence capture hang

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** fix

## What was done
- Investigated Logfire trace `019f7a7abd793435b08be07836ffe95b` and the live process
  tree after a Slack `run_review` remained open after producing its verdict and PDF.
- Reproduced the hang against the exact first evidence URL,
  `raw.githubusercontent.com/dreadfulstep/portfolio/main/README.md`.
- Isolated the hang to Playwright `page.add_style_tag()` on Chromium's native
  `text/plain` viewer.
- Replaced Playwright style-tag injection with direct DOM style creation through
  `page.evaluate()`.
- Added line-level text rectangles for large `<pre>/<code>` text nodes so raw README
  evidence can be targeted instead of being discarded as one oversized element.
- Added a 45-second hard watchdog per capture and a 240-second hard watchdog around the
  complete optional video stage. Browser close is also bounded.
- Added a metadata-only Logfire event after every successful browser screenshot with
  evidence ID, URLs, HTTP status, local path, byte size, and visible-element count. No
  PNG bytes or base64 are sent.
- Added regression tests for plain-text capture, Logfire screenshot metadata, and capture
  watchdog behavior. The full suite now has 50 passing tests.

## Why / decisions made
- Per-call Playwright defaults did not protect operations such as style injection, so a
  single hostile or unusual document could keep the Slack tool open forever.
- Raw GitHub README URLs are expected evidence, not an edge case that can simply be
  skipped. The capture path now handles them explicitly.
- Screenshot content is already supplied to the instrumented director model; the added
  Logfire event records capture completion and metadata only, as requested by the human.
- The currently hung task is executing code loaded before this fix. A process restart is
  still required to cancel it and load the repaired implementation.

## Files touched
- `src/clanker/review/video/capture.py` — modified — safe style injection, raw-text line
  geometry, bounded close, and Logfire capture event.
- `src/clanker/review/video/pipeline.py` — modified — per-capture watchdog.
- `src/clanker/review/runner.py` — modified — whole-video watchdog and timeout result.
- `src/clanker/config.py`, `.env.example` — modified — video timeout setting.
- `tests/test_video.py` — modified — raw-text, metadata-log, and timeout regressions.

## Open questions / for the human
- Restart `uv run clanker run`; the live process still contains the old hanging capture.

## Next steps
- Retry the same Slack review after restart and verify the trace shows
  `Browser screenshot captured for ...`, the director call, target resolution, encoding,
  and the MP4 upload.
