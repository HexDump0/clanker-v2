# Alibaba prompted-output validation

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Inspected the current review agent and the installed Pydantic AI 2.13.0
  `PromptedOutput` interface.
- Ran a minimal live OpenRouter request pinned to Alibaba using DeepSeek V4 Flash,
  medium reasoning, `PromptedOutput` for a small Pydantic model, and an optional tool.
- Made no application-code or configuration changes.

## Why / decisions made
- The live request succeeded and returned a validated Pydantic model with the expected
  values. This confirms prompted output avoids Alibaba's rejection of
  reasoning plus `tool_choice=required` while allowing ordinary optional tools to remain.
- For the formal reviewer, the intended change is conceptually limited to wrapping
  `ReviewOutput` in `PromptedOutput`; the runner, PDF generator, Slack delivery, and
  canonical `ReviewOutput` contract can remain unchanged.
- Validation is preserved. Malformed JSON or schema-invalid data is handled through
  Pydantic AI's output validation and the agent's configured retries, although prompted
  output is less constrained at generation time than native/tool output.

## Files touched
- `AI/journal/2026-07-19-08-alibaba-prompted-output-validation.md` — created — records
  the sanitized compatibility result.

## Open questions / for the human
- Should the next unit of work implement and test this change in the review agent?
- Should provider routing remain pinned to Alibaba after the change, or retain a
  compatible fallback for transient provider errors?

## Next steps
- If approved, change only the formal review agent's output mode and add tests covering
  validated output, invalid-output retry, ordinary tool calls, and the PDF pipeline.
- Run one real read-only certification review in staging before production rollout.
