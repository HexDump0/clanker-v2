# Enrich Dashboard and Stardance agent tools

**Date:** 2026-08-29 · **Agent:** Codex (GPT-5) · **Type:** feature

## What was done
- Removed the Dashboard-specific `clanker/0.1` user agent that Cloudflare blocked and
  retained an ordinary HTTPX request profile. Added a distinct Cloudflare block error.
- Made Dashboard session configuration accept a bare JWT, `session=...`, or a pasted
  Cookie header without persisting any captured credentials.
- Updated typed Dashboard models for attempts, historical reviews with optional ids,
  reviewer/claimer metadata, active events, requirements/permissions, AI index status,
  cache metadata, and feedback templates.
- Explicitly excluded Dashboard `aiSummary` from model serialization and all agent inputs.
- Enriched the review packet with Dashboard status, proof-video/feedback requirements,
  claim state, complete attempt/review/return history, active events, cached GitHub/README
  freshness, feedback templates, and private internal reviewer notes.
- Added a private-output guard that stops PDF/video/Slack artifact generation when a
  meaningful internal-note phrase is copied verbatim into structured public output.
- Replaced whole-page Stardance text flattening with a standard-library structured parser:
  canonical identity, author/description, hours, devlog count, default/custom banner state,
  deduplicated dated devlogs, bounded body text, and bounded content media.
- Added a focused single-devlog tool and safe same-origin redirect handling so the
  Stardance session cookie can never follow a redirect to another host.
- Added source timestamps, completeness metadata, newest+oldest retention under limits,
  exact-host validation, and structured error categories to the new Stardance results.
- Added chat-only read tools for aggregate queue statistics and Dashboard feedback
  templates. The watcher and its behavior were not changed.
- Updated agent prompts and the stable Dashboard API reference.
- Added sanitized HAR-derived response fixtures and regression tests. Also corrected the
  stale Slack announcement test to match its documented headline/embed/thread behavior
  and removed the associated no-op f-string lint error.

## Why / decisions made
- Live comparison proved ordinary HTTPX and curl profiles return JSON 200 with the same
  session for which the explicit Clanker user agent receives Cloudflare 403. Full browser
  impersonation is unnecessary.
- Current pending resubmissions can have an empty top-level `reviews[]` while all earlier
  feedback lives in `attempts[]`; preserving this history is necessary for meaningful
  re-review evidence and resubmission-spam escalation.
- Human internal notes can guide investigation, but are private and cannot become public
  evidence. Prompt instructions plus a deterministic verbatim-leak stop provide defense
  in depth; semantic paraphrase remains governed by the model instruction.
- Dashboard AI summaries were excluded entirely to avoid anchoring Clanker's independent
  judgment. AI type/index status remains diagnostic metadata, not review evidence.
- Stardance project HTML duplicates responsive cards and can exceed the former 20,000-char
  flattening limit. Parsing stable semantic classes/attributes preserves chronology and
  removes page chrome without adding another runtime dependency.
- HTTPX official guidance prefers client-scoped cookies over per-request cookie jars. A
  generic shared web client cannot safely hold the Stardance secret, so the implementation
  uses an exact-host, manual same-origin redirect loop and a per-request Cookie header,
  preventing cross-origin forwarding and avoiding the deprecated `cookies=` argument.
- The Context7 skill was selected for current library guidance, but its connector was not
  available. Official HTTPX/Pydantic documentation and installed-package behavior were
  used as the fallback.

## Files touched
- `.gitignore` — modified — ignore secret-bearing HAR archives.
- `AI/context/API.md` — modified — current attempts schema, sorting, private notes,
  report endpoint, and Cloudflare/AI-summary implementation notes.
- `src/clanker/config.py` — modified — document accepted Dashboard session formats.
- `src/clanker/shipwrights/models.py` — modified — current typed Dashboard response shape.
- `src/clanker/shipwrights/client.py` — modified — connectivity, errors, session parsing,
  README/cache metadata, and feedback templates.
- `src/clanker/shipwrights/__init__.py` — modified — export new typed contracts/errors.
- `src/clanker/review/tools.py` — modified — structured Stardance project/devlog tools,
  cookie isolation, completeness, and errors.
- `src/clanker/review/packet.py` — modified — complete Dashboard/Stardance evidence packet.
- `src/clanker/review/runner.py` — modified — private-note public-output guard.
- `src/clanker/prompts/system.md` — modified — document richer evidence and privacy rules.
- `src/clanker/prompts/chat.md` — modified — document chat-only aggregate/template tools.
- `src/clanker/service.py` — modified — register queue-statistics and template read tools
  only with the chat agent.
- `src/clanker/slack/announcer.py` — modified — remove a no-op f-string prefix.
- `tests/fixtures/dashboard_cert_detail.json` — created — sanitized current response shape.
- `tests/conftest.py`, `tests/test_client.py`, `tests/test_review.py`,
  `tests/test_announcer.py` — modified — regression coverage and stale-test correction.
- `AI/journal/2026-08-29-09-har-stardance-dashboard-audit.md` — created — initial audit.
- `AI/journal/2026-08-29-10-tool-first-scope-clarification.md` — created — watcher boundary.
- `AI/journal/2026-08-29-11-dashboard-notes-and-ai-summary-boundary.md` — created — data rules.
- `AI/journal/2026-08-29-12-dashboard-stardance-tool-enrichment.md` — created — this record.

## Open questions / for the human
- None required for use. Internal-note privacy is enforced against verbatim copying; as
  with any model instruction, semantic leakage should also be monitored in real reviews.

## Next steps
- Run one human-observed formal review when desired to evaluate how the richer attempt and
  Stardance evidence affects the model's judgment and token usage.

## Verification
- `uv run pytest -q` -> 72 passed.
- `uv run ruff check src tests` -> passed.
- `uv lock --check` -> passed.
- `git diff --check` -> passed.
- Safe live Dashboard reads -> list/detail/templates/GitHub/README all passed; captured
  detail parsed five attempts and four historical reviews, and `aiSummary` was absent from
  serialized/agent input.
- Safe live Stardance reads using current configured session -> admin redirect, structured
  project extraction, and focused devlog extraction all passed.
- No claims, reviews, reports, notes, uploads, Slack writes, or other external mutations
  were made.
