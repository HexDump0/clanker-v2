# Prompted review output implementation

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** fix

## What was done
- Changed only the formal review agent from Pydantic AI's default tool-based structured
  output to `PromptedOutput(ReviewOutput)`.
- Updated reviewer model documentation to describe the prompted, validated JSON contract.
- Added a regression test that executes the configured review agent with Pydantic AI's
  test model and verifies a validated `ReviewOutput`, prompted output mode, no output
  tools, and retention of all ordinary review tools.
- Ran the focused review tests, Ruff, the full test suite, and `git diff --check`.

## Why / decisions made
- The default bare-model output mode forces an output tool through
  `tool_choice=required`, which Alibaba rejects when reasoning is enabled.
- Prompted output removes that forced output tool while preserving the existing
  `ReviewOutput` type, Pydantic validation, configured retries, reasoning settings, and
  optional research tools.
- The chat agent was deliberately left unchanged because it returns conversational text
  and was not the source of the provider incompatibility.
- Verification passed: 6 focused tests, all 24 repository tests, and Ruff.

## Files touched
- `src/clanker/review/agent.py` — modified — selects prompted output for formal reviews.
- `src/clanker/review/models.py` — modified — updates stale output-mode documentation.
- `tests/test_review.py` — modified — adds the output-mode and optional-tools regression.
- `AI/journal/2026-07-19-09-prompted-review-output-implementation.md` — created — records
  this implementation.

## Open questions / for the human
- None blocking. A real certification review is still recommended before production
  rollout because the unit suite does not exercise a full external-model response with
  the large production schema.

## Next steps
- Run one read-only certification review in staging with Alibaba pinned and inspect the
  structured review and generated PDF.
- Rotate the OpenRouter key that was exposed in chat before production use.
