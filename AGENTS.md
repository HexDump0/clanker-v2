# AGENTS.md — clanker v2

**clanker v2** is a ground-up rewrite of **sw-clanker** (v1), an AI-assisted review bot for
Hack Club Shipwrights certifications ("ships").

## Read first: the `AI/` folder

All agent-facing knowledge lives in [`AI/`](./AI). Before doing any work:

1. Read [`AI/README.md`](./AI/README.md) — the conventions for this folder.
2. Skim [`AI/context/`](./AI/context) — API reference, v1 architecture, pain points, v2 roadmap.
3. Skim the latest entries in [`AI/journal/`](./AI/journal) — what previous agents did and why.

## The journal rule (mandatory)

**Everything an agent does must be recorded.** When you finish a unit of work (or a session),
create a **new file** in `AI/journal/` describing what you did, why, which files you touched,
decisions made, and open questions. Never edit or delete another agent's journal entries.
See `AI/README.md` for the exact format.

You may also create any files/folders inside `AI/` to save things future agents might need
(research notes, decisions, diagrams, snippets). Keep secrets out of the repo.

## Repo layout

```
clanker-v2/
├── AGENTS.md           ← you are here
├── AI/                 ← agent brain: context, journal, notes (see AI/README.md)
├── sw-reviewer/        ← v1 source, REFERENCE ONLY (own git repo, gitignored here)
├── pyproject.toml      ← v2 Python package (uv-managed)
├── src/clanker/        ← v2 source: config, shipwrights API client, watcher, CLI
└── tests/              ← pytest suite (in-memory fake dashboard, no network)
```

## Key facts

- v1 lives in `sw-reviewer/` and is **read-only reference material**. Do not modify it.
  It has its own git repo/remote (`github.com/AjayAntoIsDev/sw-reviewer`) and is gitignored
  in this repo on purpose.
- The reverse-engineered Shipwrights Dashboard API reference is at
  [`AI/context/API.md`](./AI/context/API.md). Treat endpoints marked `[MUTATING]` with care:
  never call them without explicit human sign-off.
- There is currently **no v2 roadmap/plan** — an earlier agent-inferred one was scrapped
  (see journal `2026-07-18-02`). Do not treat inferred goals as requirements; ask the human.
- Never commit `.env` files or real secrets/tokens/cookies.
