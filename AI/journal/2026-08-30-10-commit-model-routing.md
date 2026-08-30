# Commit model and provider routing changes

**Date:** 2026-08-30 · **Agent:** Codex (GPT-5) · **Type:** decision

## What was done
- Prepared and committed the model upgrades, dynamic provider-routing implementation,
  tests, research notes, context update, and this session's journal entries as one unit.

## Why / decisions made
- The human explicitly requested that the completed work be committed.
- Kept `.env` out of version control as required; `.env.example` records the safe,
  shareable configuration knobs and model defaults.

## Files touched
- `AI/journal/2026-08-30-10-commit-model-routing.md` — created — records the commit unit.
- All files listed in journal entry `2026-08-30-08-models-and-dynamic-provider-routing.md`
  are included in the same commit, along with this session's related research journals.

## Open questions / for the human
- None.

## Next steps
- Restart the deployed Clanker process when ready so it loads the local `.env` changes.
