# Slack tool-result event diagnosis

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Queried Logfire trace `019f78eaef491b6bede7bde2b56ef1cc` read-only and mapped
  its spans to the Slack streaming and nested review code paths.
- Inspected the installed Pydantic AI 2.13.0 event classes and reproduced the relevant
  attribute access locally with a synthetic `FunctionToolResultEvent`.
- Confirmed the generated review PDF exists locally and was completed at the same time
  as the successful `run_review` tool span.
- Made no application-code or configuration changes.

## Why / decisions made
- The formal review did not fail: its dashboard/GitHub calls, model rounds, structured
  output, and `run_review` span completed without exceptions. The PDF was generated.
- The Slack bridge handles `FunctionToolResultEvent` using `event.result`, but Pydantic
  AI 2.13.0 exposes the result as `event.part`. Accessing `event.result` raises
  `AttributeError: 'FunctionToolResultEvent' object has no attribute 'result'`.
- This happens immediately after `run_review` returns. The bridge's broad exception
  handler then appends `:warning: An error occurred while processing.`. Because the
  exception occurs before the file-upload branch, the completed PDF is not uploaded,
  and the outer chat agent does not receive a subsequent model turn.
- The supplied Logfire trace looks successful because the broken event-consumer code is
  outside the instrumented agent/tool spans and catches the exception itself.

## Files touched
- `AI/journal/2026-07-19-10-slack-tool-result-event-diagnosis.md` — created — records
  this diagnosis.

## Open questions / for the human
- None; the root cause is deterministic and locally reproduced.

## Next steps
- If approved, replace the stale event attribute usage and add a streaming regression
  test covering tool completion, PDF upload, final chat response, and history saving.
