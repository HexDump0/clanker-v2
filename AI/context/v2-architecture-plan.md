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

### Review agent — agentic and authoritative

Given a submission packet, the review agent:

- chooses which repository, commit, file, release, and demo evidence to inspect;
- calls read-only tools as needed;
- applies the review rubric;
- determines project type, check statuses, verdict, required fixes, and feedback;
- returns one validated `ReviewResult`.

It owns review judgment. It does not publish to Slack, generate artifacts, manage jobs,
spawn other agents, or mutate Shipwrights.

### Video planner — narrowly agentic

The video planner consumes the completed `ReviewResult`. It may choose which material
issues to demonstrate, arrange scenes, select supporting pages, and write concise
callouts. It returns a validated `VideoPlan` and cannot change the verdict or invent
findings unsupported by the review evidence.

### Browser recovery — optional, constrained agentic behavior

The normal browser executor follows `VideoPlan` deterministically. Later, if an expected
target cannot be located, a small recovery agent may inspect the current page and suggest
a replacement locator or navigation step. Its authority is limited to finding evidence
already named in the plan. Add this only after deterministic recording is reliable.

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
       Render PDF     Plan and record video
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
- path, line range, text excerpt, or page description when available;
- optional browser targeting hint;
- explanation and concrete suggested fix.

PDF and video workers must not reconstruct or reinterpret the verdict.

### Artifact

Tracks type, state, attempts, timestamps, error, storage location, hash, size, and Slack
publication state. PDF and video artifacts succeed or fail independently.

### VideoPlan

A validated list of scenes derived from `ReviewResult`. Each scene names its source
check/evidence, target URL, expected page type, navigation/locator hints, callout text,
suggested fix, and desired duration.

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

### README MVP

- Generate video for a rejected/warned README check on a public GitHub page.
- Use fixed viewport/theme and deterministic navigation from evidence.
- Highlight the relevant area and overlay the finding and suggested fix.
- Record a short WebM/MP4, close the browser cleanly, and validate existence, duration,
  and Slack size before publishing.

Use Playwright recording/screencast and locator highlighting or controlled overlays.

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
