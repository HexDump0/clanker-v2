# Screenshot-first vision director pipeline

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** feature

## What was done
- Added review-owned `VideoEvidence`: public URL, established finding, rubric category,
  and supported fix IDs. It intentionally rejects locator/presentation fields.
- Added clean Playwright evidence capture at 1280×720 with same-state visible DOM text
  rectangles, redirect/public-host guards, bounded loading, reduced motion, no credentials,
  and a narrow GitHub auth-popover cleanup adapter.
- Added a separate one-shot multimodal `VisionDirector`. It sees up to five screenshots and
  trusted review context, then returns a validated maximum of three scenes with optional
  exact `highlight_text`.
- Added strict text targeting: Unicode/quote/whitespace normalization, exact match followed
  by unique containment, nested-element collapse, and no fuzzy matching. Missing,
  ambiguous, tiny, or page-sized targets fall back to no highlight.
- Added a screenshot compositor with flat black/gray/white/red styling. Highlight scenes
  use a dim mask and red rectangle; fallback scenes remain undimmed with a bottom-right
  callout. There are no gradients, glow, pulse, or zoom effects.
- Added an end-to-end service that captures, directs once, resolves, renders with
  Playwright/ffmpeg, and writes a detailed JSON manifest containing stage timings, model
  usage when available, target results, failures, and output metadata.
- Added a generic CLI plus ferrocompiler benchmark input and saved director plan.
- Rendered `data/videos/ferrocompiler-screenshot-pipeline.mp4`: 19 seconds, 1280×720 H.264,
  910,525 bytes. Both benchmark targets resolved; no captures failed.
- Added seven video tests; the full suite now has 45 passing tests.

## Why / decisions made
- The review agent owns what is true and where the evidence page is. The vision director
  owns only editorial scene selection, callout copy, and optional visible text selection.
- The director cannot return URLs, selectors, coordinates, timing, or styling. This keeps
  one small multimodal completion safe and makes downstream behavior deterministic.
- Capture stores the current page state as input to direction and composition. There is no
  separate evidence-freshness validation or evidence-omission gate, per the human's request.
- The final video uses stored screenshots, never live-page replay, so director vision,
  target geometry, and rendered evidence all refer to the same state.
- The benchmark used the saved plan, so it exercised all production stages after direction
  with zero paid model calls. Production `VisionDirector` makes exactly one call.

## Files touched
- `src/clanker/review/models.py` — modified — added strict `VideoEvidence` contract.
- `src/clanker/prompts/reviewer.md` — modified — asks the review agent for semantic video
  evidence without presentation data.
- `src/clanker/config.py`, `.env.example` — modified — separate director model setting.
- `src/clanker/review/video/models.py` — modified — new screenshot/director/render contracts;
  legacy live-recorder contract retained for compatibility.
- `src/clanker/review/video/capture.py` — created — isolated screenshot and DOM capture.
- `src/clanker/review/video/director.py` — created — one-shot vision director adapter.
- `src/clanker/review/video/targeting.py` — created — strict text-to-box resolver.
- `src/clanker/review/video/compositor.py` — created — minimalist screenshot MP4 renderer.
- `src/clanker/review/video/pipeline.py` — created — orchestration and audit manifest.
- `src/clanker/review/video/__init__.py` — modified — exported the new public API.
- `scripts/render_review_video.py` — created — generic runnable pipeline entry point.
- `tests/test_video.py` — created — contract, targeting, capture, director, fallback, and
  pipeline tests.
- `AI/notes/video-benchmark/ferrocompiler-video-input.json` — created — benchmark input.
- `AI/notes/video-benchmark/ferrocompiler-video-plan.json` — created — saved director output.
- `AI/context/v2-architecture-plan.md` — modified — records the implemented boundaries.
- `AI/notes/video-tooling-landscape-2026-07-19.md` — modified — aligns research note.
- `README.md` — modified — documents architecture and benchmark command.

## Open questions / for the human
- The video pipeline is callable and benchmarked but is not yet automatically scheduled by
  `ReviewRunner` or uploaded in Slack; that belongs with the durable artifact-job work.
- The real configured vision provider was not called during verification, avoiding an
  unnecessary paid request. Its adapter is covered with a fake-agent test.

## Next steps
- Run one live `VisionDirector` benchmark to measure its actual token usage and compare its
  plan with the checked-in human-directed plan.
- Add video artifact state and Slack publication when the durable job/orchestrator stage is
  implemented.
