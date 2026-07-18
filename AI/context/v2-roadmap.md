# clanker v2 — roadmap & design goals

Ground-up rewrite of sw-clanker. Not started yet. This is the target; update it as
decisions get made (and journal the decision!).

## North star

Close the loop: **poll → claim → review → submit verdict** against the real Shipwrights
Dashboard API ([`API.md`](./API.md)), with a human in control of anything mutating.

## Goals (mapped from [`v1-pain-points.md`](./v1-pain-points.md))

### 1. Real dashboard integration (fixes #1)
- New async client for `https://ds.shipwrights.dev` per `API.md` (session-cookie auth).
- Claim → review → submit flow. All `[MUTATING]` endpoints (claim, review submit, notes,
  upload) go through an explicit **human-approval gate** (config-flag; start in
  "suggest-only" mode that posts the would-be verdict to Slack for one-click approval).
- Poll `GET /certifications?status=PENDING` — `stats`, `avgWait`, `oldest` come free for
  monitoring. Use the detail + `/github` + `/readme` endpoints (server-cached, cheap).

### 2. Structured outputs everywhere (fixes #2, #13)
- pydantic `output_type` on every agent — port the v1 `models.py` models (they're good,
  just unused). Verdict comes from control flow, never message-log scraping.

### 3. Real pipeline stages (fixes #3)
- Separate agents: **precheck** (cheap/fast model, instant-rejects) → **checks**
  (the 13-check rubric) → **verdict** (synthesis + PDF + review comment draft).
- Structured handoff objects between stages; each stage individually testable.

### 4. Durable state (fixes #4)
- Small local DB (SQLite) for: seen/processed certs, review jobs + results, Slack thread
  history, idempotent claim bookkeeping. Survive restarts; on boot, pick up ships that
  arrived during downtime instead of skipping them.

### 5. Concurrency (fixes #5, #6, #9)
- Bounded worker pool for reviews (e.g. 3 concurrent), queue fed by the poller.
- No sync subprocess in async code (`asyncio.create_subprocess_exec` for Typst, or
  replace with a Python-native renderer).
- Per-service supervision: one interface crashing must not kill the others.

### 6. Clean core (fixes #7, #8, #10, #14)
- Single `AppConfig`, parsed once, injected — no import-time config, no scattered
  `os.getenv`, no hidden contextvar channels (pass context explicitly into tools).
- One watcher implementation shared by all entry points.
- Delete dead code; decide: **wire browser tools up properly (visual demo verification)
  or drop them.** Leaning: keep a minimal screenshot tool, properly registered.
- No behavior enforced by prompt-pleading — enforce in control flow.

### 7. Prompt system (fixes #11, #12)
- Prompts live in versioned files loaded from disk (single source of truth), composed
  per-stage. Port the good rubric content from v1 (`checks.md`, `demo_guidelines.md`,
  `reviewer.md`) with Stardance→Shipwrights naming fixed.

### 8. Security & hygiene (fixes #15, #16)
- Timing-safe API-key compare; auth on the web chat UI; no hardcoded channel IDs
  (config); pinned dependencies; real cost rates per model (or drop cost math).

### 9. Quality of life
- Tests (unit for checks/parsing, integration with a mocked dashboard) + CI.
- Keep what was good: Slack streaming UX, Typst PDF reports, dual LLM providers,
  Logfire, Docker + GHCR.

## Non-goals (for now)

- No admin/settings endpoints (403 for reviewer sessions anyway).
- No ingestion-API work (`x-api-key` direction) unless asked.
- No multi-workplace support beyond `stardance` until the single-workplace flow is solid.

## Open questions (for the human)

1. Confirm v2 targets `ds.shipwrights.dev` directly (per `API.md`) and the old
   community-dash proxy is dropped.
2. Approval mode at launch: suggest-only (Slack approve button) vs auto-submit for
   clear-cut cases? Suggest: launch suggest-only, add auto later.
3. Keep pydantic-ai + OpenRouter/Hack Club proxy, or reconsider stack? (v1 stack works;
   rewrite is about architecture, not framework change.)
4. Deployment target unchanged (Docker on whatever runs v1 today)?
5. Slack app: reuse existing bot tokens/app, or new app for v2?

## Suggested milestones

- **M0** — repo bootstrap, AI brain (done: see journal 2026-07-18-01).
- **M1** — dashboard API client (read-only) + typed models + tests against recorded
  fixtures. Config core.
- **M2** — pipeline stages with structured outputs on one cert (`--test-ship`), PDF kept.
- **M3** — poller + worker pool + SQLite state + Slack announce/verdict UX.
- **M4** — claim/submit behind human-approval gate; web UI auth; Docker; cutover plan.
