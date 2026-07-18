# AI/ — the shared brain for agents working on clanker v2

This folder is the persistent memory of the project. Agents (and humans) use it to pass
context between sessions. **If you are an agent: read this fully, then follow the rules
below every time you work on this repo.**

## Structure

```
AI/
├── README.md           ← this file (conventions)
├── context/            ← stable reference knowledge
│   ├── API.md              reverse-engineered Shipwrights Dashboard API (the bot's toolbox)
│   ├── v1-architecture.md  how sw-clanker v1 works (the thing we're rewriting)
│   └── v1-pain-points.md   observed issues in v1 (facts, not a v2 plan)
├── journal/            ← append-only log of agent activity (ONE NEW FILE PER WORK UNIT)
└── notes/              ← free-form scratch space: research, decisions, snippets, anything
```

## The journal rule

> **Everything an agent does gets a journal entry. No exceptions.**

After completing a unit of work (a feature, a fix, a research task, a session), create a
**new file** in `AI/journal/`:

- **Name:** `YYYY-MM-DD-NN-short-slug.md` — e.g. `2026-07-18-01-repo-bootstrap.md`.
  `NN` is a sequence number for that day (check existing files, take the next one).
- **Never edit or delete existing entries** — the journal is append-only history.
- Keep entries concise but complete enough that a fresh agent with zero context can
  understand what happened and why.

### Entry template

```markdown
# <short title>

**Date:** YYYY-MM-DD · **Agent:** <model/name> · **Type:** bootstrap | feature | fix | research | decision

## What was done
- …

## Why / decisions made
- …

## Files touched
- `path/to/file` — created|modified|deleted — why

## Open questions / for the human
- …

## Next steps
- …
```

## Saving other things

Agents **may create any files or folders inside `AI/`** for things worth keeping:
research dumps, API experiments, design docs, decision records, prompt drafts, etc.

- Put stable, curated knowledge in `context/` (update these files as the project evolves).
- Put everything else in `notes/` (or a new clearly-named subfolder).
- If you create a new top-level subfolder, add one line about it to this README and to
  the root `AGENTS.md` layout diagram.

## Hard rules

1. **No secrets.** Never write tokens, cookies, API keys, or `.env` contents into `AI/`.
   Key *names* are fine.
2. **Append-only journal.** Your entry is a new file; others' entries are read-only.
3. **Keep `context/` current.** If your work changes something described in `context/`
   (architecture, roadmap, API knowledge), update those files in the same change.
4. **v1 is read-only.** `sw-reviewer/` at the repo root is reference material — never modify it.
