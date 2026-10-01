# clanker v2 architecture plan

**Status:** Human-requested plan, 2026-07-19

This plan records direction explicitly requested by the project owner. It is not the
agent-inferred roadmap that was deleted on 2026-07-18.

## Goal

Clanker watches Shipwrights for new certifications, announces them in Slack, reviews
each project, produces a canonical structured review, renders a PDF, produces an
annotated browser video explaining important issues, and publishes available artifacts
back to the Slack thread.

The workflow must be extensible, restart-safe, and failure-isolated. In particular,
browser/video failures must not invalidate a completed review or PDF.

## What is actually agentic

An agentic component is one where a model chooses actions or tools, observes their
results, and adapts what it does next.

### Review mode (2026-10-01)

`REVIEW_MODE` picks the reviewer the runner uses (`clanker.review.runner.ReviewRunner`):

- `first_layer` (default): `clanker.review.first_layer.FirstLayerReviewer`. Code facts plus one
  Jev call, then REJECT only what is confidently established, or PASS to a human
  (`FLAG_FOR_HUMAN` / "NEEDS HUMAN" in Slack). Nothing is LLM-written: the reject message
  comes from `clanker.review.reject_message` and is posted in the Slack thread for a human to
  send from the dashboard; on REJECT the code-directed reject video is rendered when
  `VIDEO_ENABLED`. `ReviewOutcome.reject_message` / `.first_layer` carry the result.
- `agent`: the DeepSeek review agent described next (plus the vision video director).

`service.build_app` only constructs the reviewer for the selected mode.

Repo hosts (`clanker.forges`): the Dashboard only caches GitHub, so for GitLab, Codeberg/Gitea/
Forgejo, Bitbucket and sourcehut the packet fetches the README from the forge itself. If the forge
can't be reached, the README counts as *unverified* and never causes a reject. The first layer reads code
excerpts and release assets for GitHub, GitLab and Gitea. Raw-link checks, reject-message links and
video scene URLs are built per forge. Every reject reason has a video scene: a live page when one
exists, otherwise a text card.

### Review agent — agentic and authoritative

Given a submission packet, the review agent:

- chooses which repository, commit, file, release, and demo evidence to inspect;
- calls read-only tools as needed;
- applies the review rubric;
- determines project type, check statuses, verdict, required fixes, and feedback;
- returns one validated `ReviewResult`.

It owns review judgment. It does not publish to Slack, generate artifacts, manage jobs,
spawn other agents, or mutate Shipwrights.

### Video director — code-only for first-layer rejections (2026-09-30)

For first-layer rejections (the Jev path; see `AI/notes/jev-eval-results-2026-09-30.md`), the
video is directed entirely by code with **no model calls**
(`clanker.review.video.template_director`, entry point
`clanker.review.video.pipeline.generate_reject_video`):

- Each reject reason maps to at most one scene. There are at most 3 scenes, in the same priority order as
  the reject message (`clanker.review.reject_message`).
- Live public pages are captured: the GitHub file at the submission commit, the README, the demo, the
  releases page, the repo, or the banner image. Reasons with no public page (raw README link, missing banner,
  "untitled") become locally rendered text cards. A live capture that fails also falls back to a text
  card showing the URL.
- Captions and fixes use the same casual Shipwright voice as the reject message, so nothing reads as AI-written.
  AI-code and AI-README scenes deliberately highlight nothing and ask for real rework
  ("small edits won't be enough"). Pointing at a telltale line would suggest deleting it is the fix.
- It looks like a reviewer's screen recording, not an explainer (`browser_compositor.py`, 2026-10-01). The
  captured screenshots are shown inside a plain browser window. Each scene opens with a click on the address
  bar and the link typed (short links) or pasted (long ones), followed by a loading bar. The cursor moves on
  curved, decelerating paths. Each page is read through: scroll a chunk, pause with the cursor following the text,
  repeat, sometimes scroll back up (capture also saves a page screenshot up to 4000 px tall). The target
  line is drag-selected, then reading continues below it. Captions are plain subtitles, and the
  fix list sits over the last page. There are no title cards, counters or spotlight dimming. A seeded RNG
  (the cert id) makes it deterministic.
- No voiceover. Music is optional (`VIDEO_MUSIC_ENABLED`). A typical 3-scene video is about 49 s and 3–8 MB (scrolling code costs
  bitrate), and takes about 65 s to render because the recording runs in real time.

The vision-model director below remains for the older DeepSeek review path.

### Video director — one-shot vision model (DeepSeek review path)

The video director is a separate vision-capable model from the review agent. Application
code first captures one clean screenshot for each material review evidence item. In one
multimodal completion, the director sees those screenshots plus the supported findings
and fixes, chooses one to three non-redundant scenes, marks evidence as primary or
corroborating, writes concise callouts, and returns the exact visible text it wants
highlighted when a useful target exists.

Its OpenRouter provider routing is configured independently from the review agent. A
review-model provider pin must never be inherited by a director model that may only be
served by a different provider.

For unpinned workloads, provider selection is dynamic through the OpenRouter-compatible
gateway (including Hack Club AI): prioritize current throughput, softly prefer reasonable
latency, enforce configurable price ceilings and required-parameter support, and retain
automatic provider fallbacks. Provider names are not hardcoded into this default policy.

It returns a validated `VideoPlan`. It has no browser tools, cannot create URLs, cannot
change the verdict or fixes, and cannot invent findings unsupported by `ReviewResult`.
It controls editorial selection and wording, not navigation, selectors, coordinates,
layout, styling, animation, recording, or encoding.

### No agentic browser recovery

Application code matches the director's requested text against the visible DOM snapshot
captured with the screenshot. It highlights only a unique safe match. If the director
returns no text, or the text is missing or ambiguous, the scene still renders with its
finding card at the bottom-right and no highlight. The initial design has no locator-
recovery agent or browser tool loop.

### Slack conversation assistant — optional and agentic

A conversational assistant may answer follow-up questions about completed reviews.
Explicit `review <URL-or-ID>` commands are parsed by application code and do not require
an LLM router.

### Non-agentic components

- watcher and new-cert detection;
- workflow/job orchestration;
- Slack announcement and publishing;
- submission packet fetching;
- validation and persistence;
- PDF rendering;
- deterministic browser navigation, overlays, recording, and encoding;
- retries, supervision, idempotency, logging, and metrics.

## High-level flow

```text
Shipwrights watcher or explicit Slack command
                    |
                    v
             Create ReviewJob
                    |
                    +----> Announce in Slack; persist thread timestamp
                    |
                    v
          Build immutable submission packet
                    |
                    v
            Run the review agent
                    |
                    v
       Validate and persist ReviewResult
                    |
             +------+------+
             |             |
             v             v
       Render PDF     Capture evidence screenshots
             |             |
             |       Run vision director once
             |             |
             |       Resolve highlight text
             |             |
             |       Compose and encode video
             |             |
             +------+------+
                    |
                    v
       Publish each available artifact to Slack
```

Application code controls the workflow. Agents never spawn other agents. Agentic workers
receive explicit inputs and return validated outputs to the orchestrator.

## Canonical contracts

### ReviewJob

Tracks one durable certification workflow:

- job ID, certification ID, trigger, and review/schema version;
- state, attempts, timestamps, and last error for every stage;
- Slack channel and parent/thread timestamp;
- packet and canonical result references;
- independent PDF/video artifact records.

Only one active automatic job should exist per certification and review version. All
stages and Slack publication must be idempotent.

### ReviewResult

The sole source of truth for all review outputs:

- schema version and project identity;
- detected project type and mismatch information;
- verdict and confidence/human-review requirement;
- every rubric check with status and reasoning;
- required fixes, feedback, and flags;
- structured evidence for each material finding;
- model/provider, usage, and completion metadata.

Every failed or warned check should carry evidence usable by humans and artifact workers:

- evidence type (`readme`, `github_file`, `commit`, `release`, `demo_page`, etc.);
- canonical URL;
- path, line range, text excerpt, or page description when actually observed;
- HTTP status or visible text actually observed during the review, when available;
- explanation and concrete suggested fix.

The review agent supplies semantic evidence and its URL, not a required video locator.
PDF and video workers must not reconstruct or reinterpret the verdict.

### Artifact

Tracks type, state, attempts, timestamps, error, storage location, hash, size, and Slack
publication state. PDF and video artifacts succeed or fail independently.

### EvidenceScreenshot

Produced deterministically before direction. It binds one review evidence ID to the
requested/final URL, HTTP status, capture timestamp, clean screenshot, and a snapshot of
visible DOM text with element rectangles. The final video always uses this stored clean
screenshot rather than replaying the live page.

### VideoPlan

A validated list of scenes returned by the vision director. Each scene references an
existing evidence ID and fix IDs, identifies primary or corroborating evidence, supplies
short title/body copy, and optionally requests an exact visible text string to highlight.
It contains no model-generated URL, CSS selector, coordinates, or visual styling.

## Durable state and failure semantics

```text
DISCOVERED -> ANNOUNCED -> PACKET_READY -> REVIEWING -> REVIEWED
                                                       |
                                           +-----------+-----------+
                                           |                       |
                                      PDF_PENDING             VIDEO_PENDING
                                           |                       |
                                      PDF_READY               VIDEO_READY
                                           +-----------+-----------+
                                                       |
                                             COMPLETE or PARTIAL
```

A completed review and PDF with a failed video is `PARTIAL`, not a failed review. Slack
receives every successful output plus a clear notice for exhausted artifact jobs.

Persist state before dispatching work. Resume incomplete stages after restart. Use
bounded exponential backoff and distinguish transient failures from permanent provider,
validation, or unsupported-evidence failures.

Start with SQLite-backed jobs for a single deployment. Keep worker interfaces
queue-shaped so a dedicated queue/database or workflow engine can replace it later.

## Isolation

Separately supervise these roles, even if some initially share a process:

1. watcher/orchestrator;
2. review worker;
3. PDF worker;
4. browser/video worker;
5. Slack publisher.

Run browser/video in a separate process or container from the start, with its own
concurrency, CPU/memory limits, timeout, temporary directory, and browser context per
job. It receives public URLs and review/video data, but no Shipwrights session, Slack
token, or AI/GitHub credential unless a narrowly scoped feature later requires one.

## Slack behavior

Watcher jobs immediately announce the ship and persist the Slack thread. Upload the PDF
and video independently as they become ready, and report partial failures without hiding
successful artifacts.

For `@Clanker review <URL-or-ID>`, application code extracts the UUID and creates or
reuses a job in this same workflow. A chat model is not used to route that command.
Follow-up questions may use the optional assistant with persisted `ReviewResult` context.

## Video delivery

### Screenshot-first MVP

- Generate videos for rejections and meaningful warnings backed by public-page evidence.
- Capture one clean fixed-viewport screenshot and visible-text/rectangle snapshot per
  material evidence item before calling the director.
- Give a separate vision model the screenshots and supported review facts in one call.
- Resolve returned highlight text programmatically: normalized exact match first, then a
  unique containing element; ambiguous or missing matches get no highlight.
- Compose from stored screenshots in the fixed minimalist template. A no-highlight scene
  places the finding card at the bottom-right over the undimmed screenshot.
- Encode a short MP4 and validate existence, codec, resolution, duration, non-black key
  frames, and Slack size before publishing.

Use Playwright for isolated capture, a controlled local composition for presentation,
and ffmpeg/ffprobe for encoding and validation.

### Expansion order

1. repository files and line-focused views;
2. commit history/authorship;
3. releases and missing/invalid binaries;
4. public demo pages;
5. constrained locator recovery;
6. optional narration, captions, chapters, and post-processing.

Generate videos initially for rejections and meaningful warnings. Approval videos can be
considered later if their value justifies browser/model cost.

## Alibaba compatibility plan

The observed crash combines reasoning/thinking with Pydantic AI's default tool-based
structured output, which forces `tool_choice=required` or a named output tool. Alibaba
deep-thinking function calling accepts only `auto` or `none`.

Preferred experiment while retaining Alibaba and reasoning:

1. use prompt-based schema output rather than an output tool;
2. keep investigation tools on `auto`;
3. ensure no forced tool choice or native JSON response format is sent in thinking mode;
4. validate as `ReviewResult` and retry with validation feedback;
5. inspect the emitted request in Logfire during a small smoke test.

Fallbacks, in order:

1. reasoning reviewer followed by a non-thinking structured formatting pass;
2. disable thinking for the reviewer and retain tool output;
3. select a model/provider verified to support forced tools plus reasoning;
4. permit an explicitly approved OpenRouter provider fallback.

Setting `tool_choice=auto` alone is insufficient while the only legal final result is an
output-tool call. Maintain a small live compatibility smoke test for normal tools,
multiple tool rounds, final structured output, validation retry, reasoning, and the exact
pinned provider configuration.

## Extensibility

Publish internal lifecycle events after committed state changes:

- `ship.discovered`, `review.started`, `review.completed`;
- `artifact.requested`, `artifact.ready`, `artifact.failed`;
- `job.completed`, `job.partially_failed`.

Future behaviors consume these events or register workflow handlers. They are not added
to the review agent prompt unless needed for review judgment.

## Delivery phases

### Phase 1 — contracts and workflow skeleton

- Finalize `ReviewJob`, versioned `ReviewResult`, `Evidence`, `Artifact`, and `VideoPlan`.
- Define transitions, idempotency keys, retry categories, and partial success.
- Route watcher and explicit Slack commands through one orchestrator.

Acceptance: a fake job can advance, fail, restart, and resume without duplicate Slack
messages or artifacts.

### Phase 2 — canonical review and provider compatibility

- Persist the canonical structured result.
- Resolve Alibaba output compatibility.
- Record model/provider/request metadata and categorize permanent/transient failures.

Acceptance: the chosen production route repeatedly completes a structured review with
reasoning and tool calls, or an explicit fallback is selected and documented.

### Phase 3 — independent PDF

- Render only from persisted `ReviewResult`.
- Track and publish PDF idempotently.

Acceptance: retrying PDF does not rerun the review agent.

### Phase 4 — README video MVP

- Create README `VideoPlan` scenes.
- Record in the isolated worker with overlays, timeout, retry, validation, and upload.

Acceptance: a video crash leaves review/PDF intact and video can be retried alone.

### Phase 5 — broader evidence and constrained recovery

- Add file, commit, release, and demo scenes.
- Add constrained recovery only where deterministic targeting is insufficient.
- Measure cost, latency, and success rate by scene type.

Acceptance: unsupported scenes are skipped/reported without invalidating other outputs.

### Phase 6 — future actions

- Add event consumers and artifact types through stable contracts.
- Revisit queue infrastructure only when observed scale or deployment requires it.

## Safety boundaries

- Do not call Shipwrights mutating endpoints without explicit human authorization.
- Treat submitted repositories and sites as untrusted input.
- Never expose sessions, tokens, keys, cookies, or personal data to page JavaScript or
  recorded output.
- Restrict browser downloads, protocols, navigation scope, filesystem access, and time.
- Do not record authenticated/private dashboards or tabs.

## Open decisions

1. Generate video only for rejects/warnings, or every review?
2. Is SQLite sufficient for the initial deployment?
3. Keep Alibaba with prompted output, split reasoning/formatting, or change route/model?
4. Ship the optional Slack assistant now or after the core pipeline?
5. What duration, format, resolution, and Slack file-size budget should video target?
