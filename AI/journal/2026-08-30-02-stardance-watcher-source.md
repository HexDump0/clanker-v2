# Add Stardance admin queue as an alternate watcher source

**Date:** 2026-08-30 · **Agent:** opencode (GLM) · **Type:** feature

## What was done
- Probed the Stardance admin ship-queue page
  (`/admin/certification/ship?status=pending&sort=newest`) live:
  - No JSON API exists (`?format=json` and `.json` both return 500) — HTML scraping it is.
  - Page carries a metrics block; `In queue` is the pending total (108 live).
  - Ships are `ship-queue__row` table rows (25/page, `limit=25`), newest first, with
    `ship-queue__project-title`, `ship-queue__project-id` (`#NNNN`), `cell-author`
    (bare text), `wait-badge`, `hours`, and `status-pill--<status>` cells. Some cells
    are duplicated for responsive layouts.
  - The "Oldest waiting" metric tile links a ship id but is not a queue row — the
    parser is row-scoped so it cannot be mistaken for one.
  - Status filter values are `pending | approved | returned | all`; filters do work
    (earlier identical-looking counts were compared too loosely; sets differ).
- Implemented a watcher source abstraction:
  - `PendingSource` protocol (`name`, `pending_page`, `resolve`) in `watcher.py`.
  - `ShipwrightsPendingSource` — previous behavior, unchanged semantics.
  - `StardancePendingSource` — polls the Stardance admin queue, detects new ships by
    (total, page-1 keys) fingerprint, then reconciles each ship to a Dashboard cert by
    `external_id` (Stardance ship id == Dashboard external_id) before emitting, because
    the review packet builder needs the Dashboard record. Ships the Dashboard has not
    imported yet are retried on every poll (including unchanged ones) and dropped after
    6 hours with a log line.
  - `Watcher` keeps all its fingerprint/seen-state logic; seen-ids are now namespaced
    by source in the state file — switching sources records the current queue first
    instead of flood-emitting it as "new".
- Selection is env-driven: `WATCHER_SOURCE=dashboard|stardance` (default `dashboard`),
  overridable per-invocation with `clanker watch --source stardance`.
- New `src/clanker/stardance.py`: `StardanceAdminClient` (ordinary HTTPX profile, no
  identifying UA, per-request Cookie header, no redirects followed) plus a stdlib
  `HTMLParser`-based queue parser.
- Live end-to-end check: first poll recorded 108 pending / 25 page-1 ships, emitted
  nothing (record-only first run), and reconciled 0/25 — expected while the Dashboard's
  Stardance import is lagging (newest Stardance ships 11076+ are absent from the
  Dashboard's pending list); those ships stay in the retry set.

## Why / decisions made
- Stardance is the source of truth for ships; watching it means the watcher sees ships
  the broken Dashboard import has not picked up yet. The Dashboard is still required for
  reviews, so emission waits for import (bounded by `RESOLVE_MAX_AGE = 6h`).
- Reconcile matches by `external_id` while walking Dashboard PENDING pages rather than
  using the `q` free-text search (titles are too generic, e.g. "nasa").
- `pages` is computed as `ceil(total / 25)` since the HTML does not expose a page count.
- Fixing the earlier bug class from journal 2026-08-29-12: no per-request `cookies=`
  argument; the session rides a `Cookie` header with redirects disabled.

## Files touched
- `src/clanker/stardance.py` — created — admin queue client + parser.
- `src/clanker/watcher.py` — modified — source abstraction, Stardance source, factory,
  source-namespaced watcher state.
- `src/clanker/config.py` — modified — `watcher_source` setting (`WATCHER_SOURCE`).
- `src/clanker/service.py` — modified — build the source from settings in
  `run_watcher_service`, close it on shutdown.
- `src/clanker/cli.py` — modified — `watch --source` / `--emit-backlog` flags.
- `tests/test_watcher.py` — modified — construct the shipwrights source explicitly.
- `tests/test_stardance_watcher.py` — created — parser, cookie/redirect behavior,
  reconcile/retry/drop, source-switch state safety (9 new tests).
- `AI/context/API.md` — modified — Stardance admin queue page notes.

## Open questions / for the human
- Whether to flip `.env` to `WATCHER_SOURCE=stardance` for production use, and whether
  the 6h resolve window is right for the Dashboard import lag.

## Next steps
- Observe one live ship flowing through Stardance watch -> Dashboard import -> review
  end to end.

## Verification
- `uv run pytest -q` -> 81 passed (9 new).
- `uv run ruff check src tests` -> passed. `uv lock --check` -> passed.
- Live read-only poll: Stardance page 1 parsed (108 total, 25 ships); Dashboard
  reconcile ran; no mutations anywhere.
