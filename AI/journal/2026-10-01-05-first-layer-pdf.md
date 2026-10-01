# First-layer PDF report

**Date:** 2026-10-01 · **Agent:** Claude Code (Opus 5.5) · **Type:** feature

## What was done
- The first-layer reviews used the old agent report: 11 of 13 rubric rows read "SKIP — not checked automatically", and
  the verdict card clipped "FLAG_FOR_HUMAN". The human asked for a new PDF.
- New template `src/clanker/templates/first_layer_report.typ` (same Hack Club dark theme). It contains:
  - a first-layer notice, the project banner, and a verdict card (REJECT, or a purple NEEDS HUMAN that fits), plus type and date;
  - links: demo, repo, README, Stardance;
  - REJECT: "Why it was rejected", one card per reason with the fix text and its evidence (Jev score against the limit,
    the CSS-rule signals, files read, the README link, demo host, release assets, banner label, ...), then "Message
    for the shipper" (template text; a Shipwright sends it);
  - NEEDS HUMAN: "What the human should look at" with the near misses;
  - "Jev scores": every question with a score bar, a white tick at the limit, and OK/CLOSE/FAIL/INFO. Questions with a limit come first;
  - "Code checks": README (and where it came from), raw link, demo host, demo render, banner, release assets
    (only where a build is expected), code sampled, modern AI CSS style, previous rejections.
- `src/clanker/review/first_layer/report.py`: `build_report_data(result, packet)`. `FirstLayerResult.thresholds`
  was added so the report can show the limits.
- `src/clanker/review/pdf.py`: shared `_compile` plus `generate_first_layer_pdf`. The agent path still uses the old report.
  The runner's first-layer path now renders the new one.
- Tests: report data for the CSS reject; two real Typst compiles, including a name/description with markup characters.
  198 tests pass. Ruff is clean.
- Live check: I regenerated reports for ISO_VERSE (REJECT, 2 pages) and Fleeting/GitLab (NEEDS HUMAN, 2 pages) and inspected them as images.

## Files touched
- `src/clanker/templates/first_layer_report.typ` (new), `src/clanker/review/first_layer/report.py` (new),
  `src/clanker/review/{pdf.py,runner.py}`, `src/clanker/review/first_layer/reviewer.py`,
  `tests/{test_ai_css.py,test_first_layer.py,test_forges.py}`.

## Notes
- The running bot needs a restart to use the new report.
