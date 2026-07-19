# Video tooling landscape for evidence-based review videos

**Researched:** 2026-07-19

## Conclusion

No researched product provides the full required workflow: accept a Shipwright review PDF
or structured result, visit arbitrary cited public pages, verify and locate the evidence,
then generate a restrained annotated review video automatically.

The market provides strong components for three separate jobs. Clanker still needs custom
glue for evidence selection, safe browser capture, and evidence provenance.

## Product categories

### PDF-to-video products

- [HeyGen PDF to Video](https://www.heygen.com/en-gb/tool/pdf-to-video)
- [Synthesia PDF to Video](https://www.synthesia.io/tools/pdf-to-video)
- [Pictory Doc to Video](https://kb.pictory.ai/en/articles/15137793-turn-a-document-into-a-video-doc-to-video)

These extract/summarize a PDF and produce narrated slides, avatars, stock visuals, or
b-roll. They do not navigate evidence URLs or visually prove review findings. They target
training and marketing content, so they are a poor fit for an evidence audit and increase
the risk of generic-looking output.

### Product-demo recorders

- [Supademo](https://supademo.com/features/demo-recorder) captures clicks/screenshots or
  uploaded media, adds hotspots and AI text/voice, and exports demos/video.
- [Arcade HTML Capture](https://www.arcade.software/html-capture) captures/editable product
  steps and exports GIF/video.
- [Guidde](https://help.guidde.com/en/collections/3533773-getting-started) turns captured
  workflows into step-based guides/videos.

These are closest visually, but their normal workflow starts with a human recording a
click path using a browser extension or desktop app. They do not take a review result and
autonomously decide which external evidence pages to capture. API access may also be tied
to higher/enterprise plans. They are useful for manual prototyping, not the core automated
pipeline.

### Managed programmatic renderers

- [Creatomate](https://creatomate.com/docs/api/quick-start/create-a-video-by-template)
  offers a visual template editor, dynamic properties/scenes, RenderScript, REST rendering,
  webhooks, and MP4 output. It is the strongest managed fit for locking the minimalist
  design while replacing text, screenshots, scene count, and durations through JSON.
- [Shotstack](https://shotstack.io/docs/api/) accepts JSON timelines with image, text,
  overlay, transition, and output instructions. It is capable, but more timeline-level;
  its older HTML asset is deprecated and has limited CSS support, making precise layout
  less convenient than Creatomate or a code-native renderer.

Both require uploading/hosting evidence screenshots where the cloud renderer can access
them, add a vendor/cost dependency, and move rendering outside Clanker's isolated worker.

### Self-hosted programmatic renderers

- [Revideo](https://github.com/midrender/revideo) is an MIT-licensed TypeScript rendering
  engine with a headless render API, dynamic inputs, browser preview, parallel rendering,
  and serverless deployment support. It is a strong licensing-friendly replacement for
  the custom HTML/Screencast composition, though it adds a Node toolchain and is less
  established than Remotion.
- [Remotion](https://www.remotion.dev/docs/renderer) is the mature React option with
  parameterized compositions and server-side `renderMedia()`. Its current licensing page
  says the free license applies to individuals and companies up to three people; automated
  video applications at companies of four or more use a company plan starting at a
  $100/month minimum. License eligibility must be checked before adoption.
- [Playwright Screencast](https://playwright.dev/python/docs/api/class-screencast) is
  already installed and can record, emit JPEG frames, and add chapters/HTML overlays. It
  is useful for browser capture but is not a full frame-accurate composition system and
  does not provide evidence planning or spotlight targeting.

## Recommended stacks

### Lowest dependency / current direction

`ReviewResult -> DeepSeek VideoBrief -> Playwright screenshots -> controlled local HTML ->
Playwright/ffmpeg`

Keep this if volume is modest and the minimalist template stays simple. It preserves the
Python-only application surface and keeps public evidence assets local.

### Best self-hosted renderer upgrade

`ReviewResult -> DeepSeek VideoBrief -> Playwright screenshots -> Revideo -> MP4`

Use Revideo if deterministic frame timing, richer layout tests, or more scene types make
the current Screencast compositor costly. It is MIT licensed but introduces Node/TypeScript.

### Fastest managed rendering path

`ReviewResult -> DeepSeek VideoBrief -> Playwright screenshots -> object storage ->
Creatomate template API -> MP4 webhook`

Use Creatomate if avoiding renderer maintenance matters more than cloud cost, external
asset handling, and vendor dependency.

## What remains custom in every viable stack

1. Convert structured review evidence (or legacy PDF text) into a strict `VideoBrief`.
2. Decide primary versus corroborating findings without changing the verdict.
3. Safely navigate arbitrary public evidence URLs.
4. Resolve and verify the target, with deterministic fallbacks.
5. Capture screenshot, target rectangle, URL, status, and timestamp together.
6. Reject stale evidence when the current page contradicts the completed review.
7. Publish the artifact with Clanker's existing job/failure-isolation semantics.

That custom evidence layer—not drawing frames—is the actual product-specific work.

