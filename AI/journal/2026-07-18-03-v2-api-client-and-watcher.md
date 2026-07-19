# v2 kickoff: typed Shipwrights API client + persistent watcher

**Date:** 2026-07-18 · **Agent:** Claude Fable 5 (Claude Code) · **Type:** feature

## What was done

First real v2 code. Replaced v1's convoluted project-fetching path (community-dash
proxy + `dash_client.py` + in-memory watcher) with a clean package targeting the
**real** Shipwrights Dashboard API (`ds.shipwrights.dev/api/v1`) — the thing it was
actually made for, per `AI/context/API.md`.

- `pyproject.toml` + `uv.lock` — uv-managed package, Python ≥3.13, deps: httpx,
  pydantic, pydantic-settings. Dev: pytest, pytest-asyncio, ruff. Console script
  `clanker`.
- `src/clanker/config.py` — single `Settings` (pydantic-settings, env/`.env`).
  Fixes v1's scattered `os.getenv` and import-time config loading.
- `src/clanker/shipwrights/models.py` — pydantic models (camelCase aliases,
  `extra="allow"`): `CertSummary`, `CertDetail`, `CertificationPage`, `Review`,
  `GitHubData`, `LeaderboardEntry`, `CertStatus`/`Verdict` enums.
- `src/clanker/shipwrights/client.py` — `ShipwrightsClient`: one shared
  `httpx.AsyncClient` (async context manager, injectable transport for tests),
  session-cookie auth, typed errors (`AuthenticationError`, `NotFoundError`;
  login-redirects surfaced as auth errors). Read methods: list (+`iter_` over all
  pages), detail, github, readme, leaderboard, workplace. Mutating methods
  (`claim`, `submit_review`, `set_internal_notes`) exist but **raise
  `MutationNotAllowedError` unless constructed with `allow_mutations=True`** —
  the safety gate AGENTS.md asks for.
- `src/clanker/watcher.py` — `Watcher` polls all PENDING pages, diffs against a
  **disk-persisted** seen-set (`data/watcher_state.json`, atomic writes). Fixes
  v1 pain point #4: restarts no longer skip ships submitted during downtime.
  First-ever run records the backlog without emitting (`WATCHER_EMIT_BACKLOG=true`
  to flip). Emits via callback — no Slack/review coupling.
- `src/clanker/cli.py` — `clanker queue | show <id> | watch`.
- `tests/` — 14 tests, all passing, against an in-memory `FakeDashboard` via
  `httpx.MockTransport` (no network). Ruff clean.
- `README.md`, `.env.example` (+ `.gitignore` exception), AGENTS.md layout updated.

## Verified live (human supplied a session cookie)

Read-only endpoints confirmed working against production Stardance on 2026-07-18:
list (203 PENDING, 5 pages, stats), detail, `/github` (cached repo+commits),
`/readme`, leaderboard. Watcher `poll_once` walked all pages and persisted 203 ids;
second poll emitted nothing (correct). Bad cookie → clean
`AuthenticationError: 401 Not logged in`. **Mutating endpoints deliberately not
exercised** (would claim a real cert).

The cookie lives only in the gitignored `.env` — never committed, per hard rule 1.
Note: session JWTs expire ~30 days; refresh from the browser when auth fails.

## Why / decisions made

- Targets `ds.shipwrights.dev` directly (open question 1 from journal 01 — implied
  yes by the human's instruction "use the api for stardance, for which it would
  actually be made for").
- Mutations behind an explicit constructor flag rather than omitted: v2's headline
  is closing the claim/submit loop, but nothing should mutate by accident.
- Cert ids are strings (UUIDs) — v1's `int(ship_id)` assumption is gone.
- `extra="allow"` on models so unknown server fields survive round-trips.
- Watcher handler failures mark the cert seen anyway (logged) — no retry storm;
  a future review-queue layer can own retries.

## Files touched

- `pyproject.toml`, `uv.lock` — created
- `src/clanker/{__init__,config,cli,watcher}.py` — created
- `src/clanker/shipwrights/{__init__,models,client}.py` — created
- `tests/{__init__,conftest,test_client,test_watcher}.py` — created
- `README.md`, `.env.example` — created
- `.gitignore` — modified (allow `.env.example`)
- `AGENTS.md` — modified (repo layout)

## Open questions / for the human

1. Poll interval default is 30 s (v1 was 15 s) — fine?
2. Session-cookie refresh: manual for now. Automate later (passkey/OAuth flow)?
3. Next milestone: port the review agent (13-check rubric) or Slack announce first?

## Next steps

- Review pipeline: per-cert packet builder (detail + github + readme) feeding an
  agent with **structured output** (fix v1 pain points #2/#3).
- Then Slack announce + claim/submit behind human approval.
