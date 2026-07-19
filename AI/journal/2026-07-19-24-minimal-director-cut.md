# Minimal ferrocompiler director cut and full workload audit

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** feature

## What was done
- Directed and rendered a new video from the ferrocompiler PDF benchmark.
- Reduced the story to two evidence scenes: submitted repository 404 (primary) and a
  zero-result GitHub repository search (corroboration).
- Built a transparent benchmark harness that captures stabilized evidence screenshots and
  composes them into a controlled local scene before recording with Playwright Screencast.
- Revised the first styled cut after human feedback into a flat minimalist treatment with
  no gradients, glow, zoom, pulse, glass effects, or decorative browser chrome.
- Wrote a detailed director audit covering every relevant input, browser interaction,
  command/tool category, code artifact, render iteration, bug, output measurement, and
  per-review workload conclusion.

## Why / decisions made
- Snapshot-first local composition prevents arbitrary live-page CSS and overlays from
  interfering with the final video while keeping the original evidence visible.
- The user explicitly preferred minimalism. The final system uses flat black/gray surfaces,
  thin lines, white type, and a single red accent.
- The GitHub user-profile 404 was removed because it repeated the repository 404 without
  adding enough decision value.
- Cached captures now preserve capture facts only; current editorial script values win so
  copy and timing edits cannot silently reuse stale fields.

## Files touched
- `AI/notes/video-benchmark/ferrocompiler-director-script.json` — created — complete
  editorial manifest for the benchmark.
- `AI/notes/video-benchmark/ferrocompiler-director-audit.md` — created — full director and
  tooling workload audit.
- `scripts/render_ferrocompiler_director_cut.py` — created — benchmark capture/composition/
  recording/encoding harness.
- `AI/journal/2026-07-19-24-minimal-director-cut.md` — created — this entry.
- `data/video-director/ferrocompiler/*` — generated, ignored — captured evidence assets.
- `data/videos/ferrocompiler-director-cut.mp4` — generated, ignored — final video.

## Verification
- `ruff check scripts/render_ferrocompiler_director_cut.py` passed.
- `uv run pytest -q` passed: 38 tests in 3.61 seconds.
- Final `ffprobe`: 17.2 s, 596,124 bytes, 1280x720, H.264, yuv420p, 30 fps.
- Extracted and visually inspected eight final frames across the timeline.
- SHA-256: `e44dcbc319ce69e90598ed03eb06a327feebc641027bfe206432d9ee6a7e9f8d`.

## Open questions / for the human
- Whether this flat minimalist direction is the desired baseline for generalizing the
  video renderer.
- Whether silent videos are sufficient or later versions should include restrained
  narration/captions.

## Next steps
- If the direction is approved, split the benchmark harness into reusable evidence capture
  and composition modules, add local fixture tests, then compile video manifests from
  structured review evidence.
