# Repo bootstrap: git init + AI brain

**Date:** 2026-07-18 · **Agent:** opencode (kimi-k3) · **Type:** bootstrap

## What was done
- Explored `sw-reviewer/` (sw-clanker v1) end-to-end: all entry points, every module in
  `sw_reviewer/`, the prompt pack, Docker/CI, `.env` key names (values never read into
  the repo).
- `git init` (branch `main`) in `clanker-v2/`.
- Created the `AI/` folder system: `context/`, `journal/`, `notes/`, with `AI/README.md`
  defining the conventions (mandatory journal entries, append-only, agents may add
  files/folders).
- Moved the reverse-engineered Shipwrights Dashboard API reference from repo root
  `API.md` → `AI/context/API.md`.
- Wrote `AI/context/v1-architecture.md` (how v1 works), `v1-pain-points.md` (16 issues,
  why the rewrite), and `v2-roadmap.md` (goals, non-goals, milestones M0–M4).
- Root `AGENTS.md` pointing future agents at the `AI/` folder and the journal rule.
- `.gitignore` — notably **gitignores `sw-reviewer/`**.

## Why / decisions made
- **`sw-reviewer/` is gitignored, not tracked/submoduled.** It is its own git repo with
  its own remote (`github.com/AjayAntoIsDev/sw-reviewer`) and is read-only reference for
  the rewrite. Tracking it here would create an embedded-repo mess. If the human wants
  it tracked (e.g. as a submodule), that's a one-line change later.
- **Key discovery that shapes v2:** v1 is *advisory-only* — it polls a read-only
  "community dash" proxy and posts verdicts to Slack; it never claims or submits. The
  `API.md` reference documents the *real* dashboard (`ds.shipwrights.dev`) **with claim +
  review-submit endpoints**, so v2's headline feature is closing that loop (behind a
  human-approval gate).
- Journal naming: `YYYY-MM-DD-NN-slug.md`, append-only.

## Files touched
- `.gitignore` — created — python/env/data ignores + `sw-reviewer/`
- `AGENTS.md` — created — repo entry point for agents
- `API.md` → `AI/context/API.md` — moved
- `AI/README.md` — created — AI-folder conventions + journal template
- `AI/context/v1-architecture.md` — created
- `AI/context/v1-pain-points.md` — created
- `AI/context/v2-roadmap.md` — created
- `AI/notes/README.md` — created
- `AI/journal/2026-07-18-01-repo-bootstrap.md` — created (this file)

## Open questions / for the human
1. Confirm v2 targets `ds.shipwrights.dev` directly and drops the old community-dash proxy.
2. Launch approval mode: suggest-only (human clicks approve in Slack) vs auto-submit?
3. Keep pydantic-ai + OpenRouter/Hack Club proxy stack?
4. Track `sw-reviewer/` in this repo (submodule) or keep it ignored as decided?
5. Repo remote: create a GitHub repo for clanker-v2?

## Next steps
- M1: typed async client for the dashboard API (read-only first) + fixtures/tests,
  central `AppConfig`. See `AI/context/v2-roadmap.md`.
