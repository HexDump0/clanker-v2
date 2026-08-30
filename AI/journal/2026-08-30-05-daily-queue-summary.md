# Daily queue summary (23:30 UTC Slack digest)

**Date:** 2026-08-30 · **Agent:** opencode (GLM) · **Type:** feature

## What was done
- Probed both source endpoints live (read-only, repo session):
  - `GET .../certifications?page=1&sort=date:asc&status=PENDING` — works;
    `projectType` is uniformly "Software" while `aiType` carries the real type
    ("iOS App", "Hardware", ...), so the summary uses `aiType || projectType`.
  - `GET .../certifications/leaderboard?range=daily` — top entry's `memberId`
    is `s:U<slackId>`, which renders as a real Slack user ping.
- Implemented the daily queue summary:
  - `src/clanker/daily.py` — `DailyStats` (pending count, "5d era" count, the
    three oldest pending certs, daily leaderboard top, praise line),
    `gather_daily_stats` (one read-only Dashboard pass), `generate_praise`
    (one-shot pydantic-ai Agent over `prompts/daily_praise.md`, Clanker/AM
    personality, canned fallbacks on any failure/missing key),
    `build_daily_summary`, `send_daily_summary`, plus `parse_daily_time` and
    `seconds_until_utc_time` scheduling helpers.
  - 5d-era counting walks `date:asc` pages and stops at the first cert newer
    than `now - 5d` (sorted oldest-first, so the walk is bounded).
  - `Announcer.announce_daily_summary` — single Block Kit embed (purple
    `#6D28D9`), sections: intro bullets ("Hello meatbags :hello:"), oldest-3
    with dashboard links + types, best shipwright ping + `:yay2:` + praise,
    `cc:` context block. Message is standalone (never threaded), so unlike the
    ship announcements the ping lives inside the embed safely (fires once).
  - `run_daily_summary_service` in `service.py` — supervised loop that sleeps
    until `DAILY_SUMMARY_TIME_UTC` (default 23:30 UTC) and posts; failures are
    logged, not fatal. Wired into `run_all` behind `DAILY_SUMMARY_ENABLED`.
  - CLI: `clanker daily` (dry-run print) / `clanker daily --post`.
  - `ShipwrightsClient.list_certifications` gained a `sort` param (verified
    against the live API).
- Post-session fixes (same day, live-testing with the human):
  - Passing a top-level `text` alongside legacy `attachments` made Slack render
    the plain-text version *above* the embed as a second message; dropped it
    (the attachment's own `fallback` covers notifications).
  - Praise prompt: removed the "you may call humans meatbags" hint (the model
    overused it) and added a binding terminology rule — submissions are
    ships/projects, a Shipwright is the *person*; never "reviewed shipwrights".
  - New `- N projects reviewed today.` bullet: sum of every reviewer's `total`
    in the daily leaderboard (`DailyStats.reviewed_today`).
- New env settings: `SLACK_DAILY_PING` (usergroup `S...` / user `U...`/`W...` /
  literal, empty = no cc), `DAILY_SUMMARY_ENABLED` (default true),
  `DAILY_SUMMARY_TIME_UTC` (default `23:30`).

## Why / decisions made
- Live probe showed `projectType` is useless ("Software" for everything);
  `aiType` is what the dashboard UI displays, so it wins when present.
- Praise generation is a separate tiny agent (plain-str output, no structured
  output tool) so the Alibaba forced-tool-choice failure mode can't apply; any
  failure falls back to one of four canned Clanker-flavored lines — the *data*
  around the praise is always real.
- Kept the user's exact wording for the intro ("Hello meatbags :hello: , here's
  todays stats", "- N projects currently pending", "the 5d era").
- Leaderboard "best" = first entry of `range=daily` (API-ordered).

## Files touched
- `src/clanker/daily.py` — created — stats gathering, praise, scheduler helpers.
- `src/clanker/prompts/daily_praise.md` — created — AM-personality praise prompt.
- `src/clanker/slack/announcer.py` — modified — `daily_ping`, `_reviewer_ping`,
  `announce_daily_summary` embed.
- `src/clanker/service.py` — modified — daily summary service + wiring.
- `src/clanker/cli.py` — modified — `clanker daily [--post]`.
- `src/clanker/config.py` — modified — three new settings.
- `src/clanker/shipwrights/client.py` — modified — `sort` param.
- `src/clanker/shipwrights/__init__.py` — modified — export `LeaderboardEntry`.
- `tests/conftest.py` — modified — FakeDashboard leaderboard route.
- `tests/test_daily.py` — created — 8 tests (gather/era5 pagination, schedule
  helpers, embed rendering incl. empty-queue/no-best/no-cc, praise fallback).

## Open questions / for the human
- The 5d era threshold and 23:30 UTC time are config'd; flip
  `DAILY_SUMMARY_TIME_UTC` if 11:30pm UTC local-perception differs.

## Verification
- `uv run pytest -q` → 93 passed (8 new). `uv run ruff check src tests` → clean.
- Live dry-run `uv run clanker daily`: 37 pending, 3 in the 5d era, oldest
  three = journeys / Hardware Based SDP Solver / macOS Sleep Disabler, best =
  Utkrishth (11 reviews), generated in-character praise line. Read-only.
- Live posts to Slack via `clanker daily --post` (4 during iteration, final one
  includes the reviewed-today bullet and single-embed fix), human-confirmed.
