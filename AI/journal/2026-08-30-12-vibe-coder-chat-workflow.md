# Vibe-coder chat workflow

**Date:** 2026-08-30 · **Agent:** Codex (GPT-5) · **Type:** feature

## What was done
- Added an additive vibe-coder handling section to the chat prompt for private
  Shipwright help threads.
- Instructed Clanker to gather source-backed evidence, separate facts from inferences,
  distinguish ordinary AI assistance from a generic no-contribution project, and give
  staff recommended handling and confidence.
- Allowed sarcastic/hostile internal commentary while requiring professional drafts for
  humans to copy manually.
- Added an explicit prohibition on using the `?<message>` delivery protocol or
  contacting the shipper directly.
- Added regression assertions covering the private-thread, evidence, draft, and
  no-direct-contact rules.

## Why / decisions made
- This is an additional chat use case; the existing Clanker personality, review-bot
  responsibilities, rubric, and formal review pipeline were preserved unchanged.
- The prompt tells Clanker to use read-only investigation tools for evidence and to
  invoke `run_review` only when a human explicitly requests the official workflow.
- User-facing drafts are deliberately separated from hostile internal commentary so
  staff can copy professional wording without exposing the private discussion.

## Files touched
- `src/clanker/prompts/chat.md` — modified — added the private help-thread workflow and
  strict no-direct-user-contact boundary without deleting existing prompt text.
- `tests/test_review.py` — modified — added chat-prompt regression assertions.
- `AI/journal/2026-08-30-12-vibe-coder-chat-workflow.md` — created — records this work.

## Open questions / for the human
- None for this prompt-only change.

## Next steps
- Live-test the workflow in a private help thread and tune the evidence format if the
  resulting internal assessments are too verbose or too soft.

## Verification
- `uv run pytest -q` — 97 passed.
- `git diff --check` — clean.
