# Feature and product audit — 2026-08-29

## Scope

This is a product review, not a security review. It asks how Clanker can save more
reviewer time, catch more real submission problems, make re-reviews easier, and give
submitters more useful feedback. These are recommendations, not inferred requirements;
the human owner should choose the roadmap.

## Executive conclusion

Clanker's core analysis pipeline is already unusually complete: it gathers dashboard,
GitHub, README, repository, Stardance, and browser evidence; returns a structured
13-check verdict; and produces PDF/video artifacts. The missing layer is the actual
reviewer product around that analysis.

The best next move is **not another report format or more generic prompt rules**. Build a
human-in-the-loop review cockpit in Slack, make reviews revision-aware, and add executable
functional checks by project type. Then expose the safe preflight portion as a submitter
self-check.

## What the current product does well

- One command/process can watch the queue, collect a rich packet, run the review, and
  publish an outcome.
- The review output is structured rather than scraped from prose: verdict, 13 checks,
  required fixes, feedback, flags, and browser-visible evidence.
- The packet fetches independent sources concurrently and gives the agent tools for deeper
  investigation.
- The review is advisory-only today, which is a good stage for measuring quality before
  tighter dashboard integration.
- There is already a serious historical benchmark and a useful manually adjudicated slice.

## Product evidence from the repository

### The benchmark says to prioritize functional coverage and escalation

`data/bench/results.jsonl` currently contains 433 scored historical certifications. The
local scorer reports:

- 58.0% raw agreement under its "correct-if-safe" policy.
- 92.2% agreement on human-approved ships.
- 25.0% agreement/recall on human-rejected ships; 166 historical rejections were approved
  by the bot.
- 79.2% measured reject precision. Manual adjudication of all 15 apparent false rejects
  found the bot correct in 14, raising estimated reject precision to 98.6% for that small
  audited slice.
- 96 seconds median review time and 143.8 seconds p90.

The human verdicts are therefore noisy ground truth, but the directional result is clear:
Clanker is conservative about rejecting, rarely escalates (1.4%), and misses many problems
that historical reviewers caught. The dashboard groups those misses mainly into README
issues (51), broken demos/links (42), functionality/bugs (21), AI/authorship (15), and
CLI/release policy (14).

That argues for deterministic checks, actual product exercise, and calibrated escalation.
It does not argue for simply making the model more eager to reject.

### The Slack experience is a notification feed, not a review workspace

`src/clanker/slack/announcer.py` posts a project card, replaces its status with one sentence
of reasoning, then uploads a PDF and optional video. Reviewers cannot inspect individual
failed checks inline, edit the feedback, re-run a check, record disagreement, claim the
ship, or submit the final decision from the message.

`src/clanker/slack/app.py` only handles free-form mentions. Even a direct review request is
routed through the chat model to a `run_review` tool rather than through a visible,
deterministic command/action.

Slack supports interactive buttons and menus in messages, modals, and App Home, so the
existing delivery surface is capable of becoming the reviewer UI without first building a
separate web app. See [Slack Block Kit](https://docs.slack.dev/block-kit/) and the
[interactivity overview](https://docs.slack.dev/interactivity/).

### Re-submissions are not a first-class workflow

`src/clanker/watcher.py` polls only `PENDING` and permanently deduplicates by certification
ID. The dashboard API explicitly allows `RETURNED` certifications to be claimed for
re-review, and the same cert retains its prior reviews and return reason. A returned cert
can therefore be absent from automatic review, while a same-ID revision can remain
suppressed by `seen_ids`.

The packet includes previous review prose, but the result has no baseline commit SHA,
revision identity, changed-file list, or "previous blocker resolved" status. Mature review
tools perform incremental reviews on new changes; CodeRabbit, for example, documents that
subsequent reviews focus on new commits. See its
[review overview](https://docs.coderabbit.ai/guides/code-review-overview).

### The expensive artifact is not the most actionable artifact

`src/clanker/review/runner.py` always performs the full agent review, then PDF generation,
then optional video generation. There is no saved review record, HTML evidence view,
single-check rerun, or artifact-only retry.

For debugging interactive web behavior, a trace can be more useful than a rendered video:
Playwright traces retain each action, DOM snapshots, console output, and network requests.
Playwright itself recommends traces over videos/screenshots for CI diagnosis. See
[Playwright debugging](https://playwright.dev/docs/debug) and
[best practices](https://playwright.dev/docs/best-practices).

## Recommended feature backlog

### P0 — Interactive reviewer cockpit in Slack

Turn each completed review into a compact action card:

- Verdict recommendation, confidence, elapsed time, and revision reviewed.
- Blockers first, each with status, evidence, and a deep link to the demo, file, commit, or
  trace step.
- Expandable warnings/suggestions instead of forcing reviewers into the PDF.
- Buttons: **Claim**, **Approve draft**, **Reject draft**, **Needs human**, **Re-run**, and
  **Why?**
- Approve/reject opens a modal with editable, copy-ready feedback. The reviewer sees the
  exact final comment and explicitly confirms before the existing dashboard client submits
  it.
- A feedback control on each finding: useful, wrong, duplicate, or rule outdated.

Why first: the code already does the analysis and already implements gated `claim()` and
`submit_review()` calls. This feature closes the gap between "bot posted a report" and
"reviewer completed a ship." GitHub's AI review UI similarly supports per-comment
feedback, re-review, and review controls; Slack already provides the UI primitives. See
[GitHub Copilot code review](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/request-a-code-review/use-code-review).

Likely code surfaces: `slack/announcer.py`, `slack/app.py`, `service.py`, a persisted review
store, and the existing mutating client methods. Dashboard mutations must remain explicit
human actions.

### P0 — Revision-aware resubmission review

Treat a review as `(cert_id, revision)` rather than simply `cert_id`:

- Watch both `PENDING` and `RETURNED`, and emit status/revision transitions.
- Save the reviewed head SHA, cert `updatedAt`, review count, prior verdict, and prior
  blockers.
- On resubmission, compare the previous SHA to the current SHA and show changed commits and
  files. GitHub's compare endpoint returns both commits and changed-file data; see
  [Compare two commits](https://docs.github.com/en/rest/commits/commits#compare-two-commits).
- Produce a resolution table: **fixed**, **still failing**, **regressed**, **new issue**.
- Default to an incremental review of changed evidence, with **Full re-review** available.

Why first: rejections create a second user journey. A bot that explains what was fixed is
far more useful than one that repeats the entire initial review.

Likely code surfaces: `watcher.py`, `review/packet.py`, `review/models.py`, GitHub tools,
and the persisted review store.

### P0 — Project-type functional test packs

Move beyond "the page rendered" into safe, bounded evidence gathering. Start with the
largest benchmark segment, Web Apps (310/433 scored ships):

- Capture page/console/network errors and failed resource requests.
- Discover a small set of visible controls and exercise a bounded happy path.
- Check navigation, forms, obvious buttons, signup/login availability, and a mobile
  viewport.
- Save a Playwright trace and screenshots around failures.
- Use auto-retrying web assertions so asynchronous pages are not marked broken too early;
  see [Playwright assertions](https://playwright.dev/docs/test-assertions).

Then add adapters selected by detected project type:

- CLI/package: verify a release/package exists, install in a disposable environment, run
  `--help`, and exercise README commands.
- API: discover OpenAPI/Swagger, call health/read-only example endpoints, and report schema
  or response failures.
- Desktop/mobile/game: validate downloadable release assets and install/run instructions;
  request human review when execution is not safely automatable.
- Bot/extension/mod/hardware: dedicated evidence checklist and a clear human handoff.

The current official Shipwrights rules vary substantially by project type—web apps need a
live URL, executables need release binaries, APIs need testable docs, and bots must be live
with documented commands—so one generic 13-check pass cannot cover them equally well. See
the current [Hack Club Shipwrights review helper](https://github.com/hackclub/shipwrights/blob/main/sw-ai/Source/helpers.py).

### P0 — Human correction and evaluation loop

Make every completed human review improve the next version:

- Store Clanker's recommendation, the final human verdict/comment, reviewer edits, finding
  votes, disagreement category, prompt/rules version, model, revision, latency, and tokens.
- Distinguish "human overrode a correct bot" from "bot error" through lightweight
  adjudication; the current 14/15 audit proves raw agreement is not enough.
- Track per-project-type and per-check precision/recall, escalation rate, reviewer edit
  distance, and time saved.
- Turn representative cases into a versioned eval dataset and require candidate prompt,
  model, and test-pack changes to beat the current baseline. Pydantic Evals supports typed,
  versionable YAML/JSON datasets and custom evaluators; see
  [dataset serialization](https://ai.pydantic.dev/evals/how-to/dataset-serialization/).

This should replace model-managed "memory" for formal review policy. Reviewer preferences
can be proposed as learnings, but a human should accept/edit them and their usage should be
visible. CodeRabbit's learnings UI is a useful product reference:
[Learnings](https://docs.coderabbit.ai/knowledge-base/learnings).

### P1 — Submitter self-check before entering the queue

Expose the deterministic and low-risk portion as `/clanker preflight <ship-or-repo>` or a
small web/Slack workflow:

- Validate repo/README/demo URLs and project-type delivery requirements.
- Show a checklist of what will block certification and direct fixes.
- Never call it an official verdict; clearly separate "ready to submit" from reviewer
  approval.
- Allow rerunning after fixes and show only changes.

This prevents avoidable rejection loops and reduces queue pressure. Shipwrights' own AI
helper already tries to tell reviewers how to test a project; Clanker can differentiate by
giving submitters executable evidence before submission rather than another summary after
submission.

### P1 — Fast preflight, standard review, deep review

The 96-second median is acceptable for background automation but poor for an interactive
reviewer loop. Split review effort:

1. **Preflight**: deterministic URL/release/README checks and project-type classification;
   target under 10 seconds.
2. **Standard**: normal agent review with bounded functional exercise.
3. **Deep**: extra browsing/tool rounds, selected by the reviewer or automatically for
   ambiguous/high-impact cases.

Finish obvious blockers after preflight, and run deep review only where it can change the
decision. GitHub's current review product similarly exposes Lite and Balanced effort levels,
which validates the UX pattern even though Clanker's thresholds should come from its own
benchmark.

### P1 — Persisted review page and contextual Q&A

Save a review result and expose a stable, linkable HTML view:

- Checks, evidence, screenshots/traces, model/rules/revision, and artifacts.
- Comparison with the previous review.
- Reviewer actions and correction history.
- "Ask about this review" in its Slack thread, automatically grounded on the saved packet
  and result rather than only the conversation text.
- Selective actions: refresh evidence, recheck demo, rerun one check, regenerate PDF, retry
  video, or full re-review.

PDF remains useful for export. Video should be generated on demand or only for material
browser-visible failures until analytics show reviewers regularly use it.

### P1 — Queue cockpit and digest

Use data the list API already returns for an App Home view and scheduled digest:

- Pending/returned counts, average wait, oldest ship, type mix, current jobs, failures, and
  estimated throughput.
- Filters for oldest, returned, type, instant-blocker likelihood, and human-review flags.
- Reviewer assignment/claim state and "continue my reviews."
- Stage progress, ETA, cancel, and retry for running Clanker jobs.

This is a much smaller product than a standalone dashboard because Slack App Home can use
the same Block Kit components as messages and modals.

### P2 — Feedback composition and template integration

- Import the dashboard's shared/personal feedback templates.
- Generate two layers: required blockers and optional encouragement/suggestions.
- Show exactly which evidence supports each requested fix.
- Produce a concise reviewer-editable comment and a more detailed submitter report.
- Add tone presets for formal review versus playful chat; formal feedback should remain
  consistent regardless of the general bot persona.

### P2 — Product analytics

Measure outcomes rather than artifact count:

- Median human time from announcement to final decision.
- Queue wait reduction and re-review turnaround.
- Percentage accepted without edits, edit distance, and override reasons.
- Precision/recall by type and check after adjudication.
- Preflight issues fixed before submission.
- Opens/clicks for inline evidence, HTML, PDF, and video.
- Cost and latency per completed human decision, not merely per model call.

## Suggested build order

1. **Review record + revision identity** — the minimum data foundation.
2. **Inline Slack result + feedback buttons** — immediately learn what reviewers use.
3. **Human-confirmed claim/submit modal** — close the reviewer loop.
4. **Returned/revision watcher + incremental comparison** — support the full lifecycle.
5. **Web App functional test pack with trace evidence** — attack the largest quality gap.
6. **Eval gate and analytics** — compare changes against real corrections.
7. **Submitter preflight** — expose the proven deterministic portion.
8. Expand test packs and add queue/App Home views based on usage.

## What I would defer

- More PDF styling or video polish before measuring whether reviewers use either artifact.
- Autonomous approval/rejection without a reviewer confirmation step.
- A large standalone dashboard before trying Slack Home, messages, and modals.
- Adding many more prose-only rubric checks to the same agent prompt.
- Model switching as the primary roadmap. The benchmark shows workflow and evidence gaps
  that a model swap alone will not solve.

## Open product decisions

- Is Clanker's primary user the reviewer, the submitter, or both? The recommendation assumes
  reviewer-first, then a bounded submitter self-check.
- Should Clanker be allowed to claim and submit after a human clicks confirm, or remain
  advisory-only indefinitely?
- Which reviewer decisions count as ground truth, and who adjudicates disagreements?
- Which project type should follow Web Apps for functional test packs?
- Is generated video a required deliverable, or an optional explanation artifact?
