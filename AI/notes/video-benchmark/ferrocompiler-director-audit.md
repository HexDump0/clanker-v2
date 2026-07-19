# Ferrocompiler video director audit

**Date:** 2026-07-19  
**Input:** `/home/ajayanto/Downloads/review_report (3).pdf`  
**Final output:** `data/videos/ferrocompiler-director-cut.mp4`  
**Purpose:** expose the real directing, browsing, coding, rendering, and revision workload.

## Final editorial decisions

- Tell one story: the submitted repository is inaccessible, so the review cannot proceed.
- Use the submitted repository 404 as the only primary evidence.
- Use the zero-result GitHub search only as corroboration; explicitly say it is not a
  second rejection reason.
- Omit the GitHub user-profile 404 from the earlier demo because it repeats the same point.
- Put the exact source URL on every evidence scene.
- Remove GitHub's unrelated sign-in flyout from the evidence capture.
- Keep the final cut silent and readable without narration.
- Use no gradients, glow, zoom, pulsing, glass effects, decorative browser controls, or
  pill-shaped badges. The final visual vocabulary is flat black/gray, thin rules, white
  type, and one red accent.

## Scene list and authored timing

1. Intro — 2.4 s — project, verdict, and one-sentence reason.
2. Submitted repository 404 — 5.8 s — primary proof and direct fix.
3. GitHub search zero results — 5.5 s — corroboration and URL-check fix.
4. Required fixes — 3.5 s — two-item resubmission checklist.

Total authored duration: 17.2 seconds. Crossfades are 0.18 seconds and there is no other
editorial motion.

## Director inputs consulted

- `AI/README.md`, the current v2 architecture plan, recent journal entries, and the
  existing video MVP source.
- Text extracted from the PDF with `pdfinfo`, `pdftotext -layout`, and visual inspection.
- The earlier `data/videos/ferrocompiler-review.mp4`, probed with `ffprobe` and sampled
  with `ffmpeg`. It was 37.36 s at 1280x800 and repeated the 404 point three times.
- Live public pages:
  - `https://github.com/idident/ferrocompiler`
  - `https://github.com/search?q=ferrocompiler&type=repositories`

## Live browser work performed in this directing session

The director used Playwright with Chromium's full headless channel, a 1280x720 or
1440x900 fixed viewport, reduced motion, blocked service workers, dark color scheme, no
credentials, and no accepted downloads.

1. Exploration run: navigated to both live URLs and printed response status, title, body
   excerpt, and image metadata. Result: repository URL returned HTTP 404; search returned
   HTTP 200 with `Your search did not match any repositories`.
2. Locator investigation: revisited the repository 404 and inspected large image bounds.
   Identified the semantic selector `img[alt^="404"]` and its visible rectangle.
3. Clutter investigation: revisited the repository 404, traced `Sign in to GitHub` through
   its ancestors, and identified `.auth-form-body.Popover` as the unrelated flyout to hide
   during screenshot capture.
4. Evidence capture: navigated once to each live URL, waited 1.2 s after DOM content load,
   resolved the chosen target, recorded its bounding box, and saved a stabilized PNG.

Total live navigations by this directing session: five. There was no autonomous browser
agent loop, no vision-model call, and no second LLM call for planning or copywriting.

## Code and data authored

- `AI/notes/video-benchmark/ferrocompiler-director-script.json` — 46 lines / 1,745 bytes.
  This is the complete human-readable editorial input: sources, targets, copy, order,
  callout sides, fixes, and timing.
- `scripts/render_ferrocompiler_director_cut.py` — 352 lines / 15,372 bytes. It handles:
  URL allowlisting, evidence navigation, locator resolution, screenshot capture, capture
  metadata, local HTML composition, canvas dim/highlight, Playwright Screencast recording,
  ffmpeg encoding, and ffprobe reporting.
- Ignored runtime evidence under `data/video-director/ferrocompiler/`: two PNG captures
  and `captures.json` with status/title/URL/time/target rectangles.
- Ignored final runtime video: `data/videos/ferrocompiler-director-cut.mp4`.

The 352-line renderer is benchmark/prototype code and includes all embedded HTML, CSS,
and JavaScript. It is not a fair estimate of per-review work: once generalized, normal
reviews should only produce a small manifest like the 46-line JSON.

## Tools and commands used

- Repository/context inspection: `sed`, `find`, `rg`, `git status`, `git diff`, `wc`,
  `sha256sum`.
- PDF inspection: `pdfinfo`, `pdftotext`.
- Browser exploration/capture/rendering: Python 3.13, Playwright 1.61, Chromium full
  headless via `channel="chromium"`, `page.goto`, locators, `page.screenshot`, and the new
  `page.screencast` API.
- Video encode/validation/frame extraction: `ffmpeg`, `ffprobe`.
- Code validation: `ruff check`, `ruff format`, Python `py_compile`, and the repository's
  complete `uv run pytest -q` suite (38 passed).
- Visual QA: eight frames extracted from each relevant cut, assembled into contact sheets,
  then inspected at contact-sheet and original-frame resolution.
- File creation/editing: repository patch tool only; runtime captures are written by the
  benchmark script.

## Iterations, including discarded work

### Cut A — rejected visual direction

- 20.866 s, 1,258,845 bytes.
- Used an ambient gradient, rounded floating browser chrome, glow/pulse highlight, subtle
  zoom, rounded callout, and two accent colors.
- Eight sampled frames looked internally consistent, but the user correctly identified
  the treatment as too stylized/sloppy rather than minimalist.

### Cut B — minimalist redesign

- 19.633 s, 560,232 bytes.
- Removed gradients, glow, pulse, zoom, glass effects, traffic-light controls, pill badge,
  large corner radii, and drop shadows. Reduced the palette to flat neutrals and red.
- Frame inspection exposed an unwanted black tail from Screencast timing.

### Cut C — timing fix exposed cached-data bug

- 18.9 s, 651,601 bytes.
- Added an explicit ffmpeg duration cap, but the render still used old scene durations
  embedded in cached `captures.json`. This showed that editorial fields and captured
  evidence metadata had been coupled incorrectly.

### Final cut

- Fixed capture reuse so the current checked-in director script overwrites cached
  editorial fields while preserving only capture facts.
- 17.2 s, 596,124 bytes, 1280x720, H.264, yuv420p, 30 fps, no audio.
- SHA-256:
  `e44dcbc319ce69e90598ed03eb06a327feebc641027bfe206432d9ee6a7e9f8d`.
- Eight final timeline frames inspected; both evidence targets, all copy, both URLs, the
  outro, and the final non-black frame were verified visually.
- Repository regression suite passed: 38 tests in 3.61 seconds.

## Work estimate learned from this benchmark

- The expensive part was developing and correcting the reusable visual system, not
  directing this particular review.
- Per-review directing data is small: two URLs, two anchors, two short callouts, two fixes,
  ordering, and timing. A small model could emit that manifest in one structured response
  if the review result already carries URLs and evidence text.
- The live-browser part required five navigations during development, but production
  should need one capture navigation per selected scene (two for this review).
- Visual QA still matters. Successful encoding did not reveal the rejected visual style,
  Screencast black tail, or cached-timing bug; sampled-frame inspection did.
