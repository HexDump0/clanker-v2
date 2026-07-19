# Video walkthrough recorder MVP (pass 2) + hand-directed demo

**Date:** 2026-07-19 · **Agent:** Claude (Fable 5) · **Type:** feature

## What was done
- Agreed with the human on a two-pass video pipeline design: an agentic "video
  director" (pass 1, not yet built) browses the submission with tools and emits a
  validated `VideoScript`; a deterministic recorder (pass 2, built here) replays that
  script in a recorded browser. The human explicitly rejected a fixed evidence-kind
  taxonomy — the director must be free to decide where to go and what to highlight for
  any reject reason.
- Built `src/clanker/review/video/`:
  - `models.py` — `VideoScript` / `Scene` / `SceneTarget` (text | selector | viewport
    targeting; exactly one required).
  - `overlay.py` — injected JS: dim mask + pulsing spotlight drawn on a full-viewport
    `<canvas>` inside a force-promoted (`translateZ(0)`) max-z fixed layer, plus a DOM
    callout card (badge / title / body). Text targeting uses a TreeWalker with a
    descend-to-deepest-element fallback for snippets spanning multiple nodes.
  - `recorder.py` — Playwright context with `record_video`, title card, per-scene
    goto → locate → smooth-scroll → draw → hold → hide, required-fixes outro card,
    ffmpeg WebM→H.264 MP4 encode. Failed scenes are skipped (logged, reported in
    `RecordingResult.skipped_scenes`); the video only fails if every scene fails.
- Demoed end to end on the real `ferrocompiler` rejection (repo 404): hand-authored the
  script (acting as the director) with three scenes — repo URL 404, user profile 404,
  GitHub search 0 results — producing `data/videos/ferrocompiler-review.mp4`
  (~37 s, 1.4 MB, all scenes rendered).

## Why / decisions made
- **Two-pass instead of recording the agent live:** Playwright recording can't pause;
  agent thinking time and backtracking would be dead air in the video. Replay is smooth
  and gives per-scene failure isolation for free.
- **Canvas mask, not DOM:** this was hard-won. Large fixed overlay elements (giant
  box-shadow spread, full-width dim panels, class-styled or inline, four-panel or
  single) rasterize patchily or not at all in headless Chromium's screencast on some
  pages (reproduced on GitHub's 404 page; the search page was fine). Screenshots and
  video capture also disagree. Drawing the dim/spotlight into a `<canvas>` bitmap
  inside a `translateZ(0)`-promoted layer composites reliably everywhere. Keep this —
  do not "simplify" back to box-shadow/panel masks without re-testing recorded video on
  the GitHub 404 page specifically.
- Overlay text is set via `textContent` and the overlay never reads page data — safe on
  untrusted demo pages; callout copy can't inject either.
- Known quirk: elements in the browser top layer (popovers/dialogs) and page elements at
  z-index 2147483647 can't be dimmed (GitHub's 404 sign-in prompt). `draw()` closes open
  popovers/dialogs best-effort; GitHub's prompt survives that. Acceptable.

## Files touched
- `src/clanker/review/video/{__init__,models,overlay,recorder}.py` — created — pass-2
  recorder MVP.
- `data/videos/ferrocompiler-review.mp4` — created — demo output (not committed).

## Open questions / for the human
- Approve the two-pass architecture update to `AI/context/v2-architecture-plan.md`
  (the plan's current "video planner consumes structured Evidence" section predates the
  human's request for a fully general director agent).
- Video budgets (duration/size), reject-only gating, and where videos should live.

## Next steps
- Build the director agent (pass 1): browser tools (goto/observe/find_text/mark_scene),
  vision path for demo pages, emits `VideoScript`.
- Wire recorder into `ReviewRunner` behind failure isolation like the PDF, and Slack
  upload.
- Tests: models validation, overlay targeting against fixture HTML, recorder with a
  local static server (avoid GitHub dependence in CI).
