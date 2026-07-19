# clanker v2

Ground-up rewrite of **sw-clanker**, the AI-assisted review bot for Hack Club
Shipwrights certifications. v1 lives in `sw-reviewer/` (read-only reference);
agent-facing project knowledge lives in [`AI/`](./AI) — start with
[`AGENTS.md`](./AGENTS.md).

## What exists so far

- `src/clanker/shipwrights/` — typed async client for the real Shipwrights
  Dashboard API (`ds.shipwrights.dev/api/v1`), session-cookie auth, pydantic
  models. Mutating endpoints (claim / submit review / notes) are implemented
  but refused unless the client is constructed with `allow_mutations=True`.
- `src/clanker/watcher.py` — polls the PENDING queue (all pages) and emits new
  certs via a callback. Seen-state persists to `data/watcher_state.json`, so
  restarts don't re-announce or skip ships.
- `src/clanker/config.py` — all configuration in one `Settings` class
  (env / `.env`), nothing reads `os.getenv` directly.
- `src/clanker/cli.py` — small CLI for poking at it.

Not ported yet: the review agent, Slack, PDF reports.

## Setup

```sh
cp .env.example .env   # paste your dashboard session JWT into SHIPWRIGHTS_SESSION
uv sync
```

## Usage

```sh
uv run clanker queue                 # pending queue + stats
uv run clanker queue --status APPROVED --page 2
uv run clanker show <cert-id>        # full cert detail as JSON
uv run clanker watch                 # poll for new pending certs (logs only)
```

## Development

```sh
uv run pytest        # tests run against an in-memory fake dashboard
uv run ruff check src tests
```
