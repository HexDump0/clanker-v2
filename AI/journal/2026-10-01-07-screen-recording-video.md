# Reject video as a human-looking screen recording

**Date:** 2026-10-01 · **Agent:** Claude Code (Opus 5.5) · **Type:** feature

## What was done
- The human wanted the video to "not seem too AI": it should look a bit like a real person using a browser, but
  keep the text overlay. The old compositor was a polished explainer (an intro title card, a dimmed spotlight,
  red-accent callouts, an uppercase kicker, "01 / 03" counters, a "Required fixes." outro). Those are the AI tells.
- New `src/clanker/review/video/browser_compositor.py` (reject path only; the agent path keeps `compositor.py`):
  - a plain light browser window (tab with title, spinner while loading, address bar, SVG icons). The human
    pointed out that the first text-glyph arrows looked bad, so all the icons are now Material-style SVGs and forward is greyed out;
  - a timeline planned in Python from a seeded RNG (cert id) and played back by the page. It opens from a new tab;
    each scene clicks the address bar, types short links key by key (with uneven timing) or pastes long ones,
    shows a loading bar, then skims long pages in wheel chunks or drag-selects the target text (blue
    selection, I-beam cursor). Cursor moves are curved Bézier paths with a Fitts-like duration and idle drift;
  - plain subtitle captions (top when the selection is low), and a "To fix before reshipping:" list over the last page.
- `capture.py`: also saves a page screenshot up to 2400 px tall (`EvidenceCapture.page_screenshot_path/page_height`).
  Element boxes for text-level tags now use the text extent (`Range`), so selections hug the words.
  `targeting.py`: nested matches tolerate boxes poking 1–2 px outside their wrapper (90% overlap).
- `compositor.render_composition` calls `window.__clankerStart()` once the screencast starts, so no frames are lost.
- `template_director.py`: "README link isn't raw" now opens the link the shipper actually set (the
  non-raw page), and the caption gives the raw URL. Text cards are a plain white text page (they appear inside the
  browser). A failed capture keeps the card text.
- Tests: `tests/test_browser_compositor.py` (determinism, typing vs paste, scroll, selection, no explainer
  tells). `test_template_director.py` was updated. 214 pass (run with a valid `VIDEO_ENABLED`; see below).
- Rendered a 3-scene sample on ISO_VERSE (non-raw README link, AI CSS, thin README): 39 s, 3.3 MB, about 55 s to render.
- Follow-up from the human: "scroll and go through the stuff a bit more". Each scene is now a reading session
  (`_Plan.browse`): scroll a chunk (1–3 wheel ticks), pause 0.5–1.4 s while the cursor drifts along the text, repeat for
  about the caption's reading time plus 1–3 s (max 11 s). There is a 15% chance to scroll back up to re-read. At the bottom it glances back up and stops.
  After a drag-selection it keeps reading below. Page captures go up to 4000 px. The sample is now 49 s and 7.8 MB.
  The READMEs are read to the bottom, and style.css goes from line 1 to about line 80.

## Open questions / for the human
- The local `.env` has `VIDEO_ENABLED=trues` (a typo). Settings fail to load, so the bot won't start and one test
  fails. It should be `true`. The file was left untouched.
- Background music (on by default) is itself an "AI video" tell; a screen recording is usually silent. Turn it off?
- The video is longer than before (49 s vs about 25 s for 3 scenes) and up to about 8 MB when scrolling code (H.264 at CRF 20).

## Files touched
- `src/clanker/review/video/{browser_compositor.py (new),capture.py,compositor.py,models.py,pipeline.py,
  targeting.py,template_director.py}`, `tests/{test_browser_compositor.py (new),test_template_director.py}`,
  `AI/context/v2-architecture-plan.md`.
