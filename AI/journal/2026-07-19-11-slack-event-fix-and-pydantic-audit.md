# Slack event fix and Pydantic AI audit

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** fix

## What was done
- Fixed Slack streaming tool completion to read `FunctionToolResultEvent.part`, matching
  the installed Pydantic AI 2.13.0 API.
- Added streaming regression coverage for a successful `run_review` completion, Slack
  timeline updates, PDF upload, stream shutdown, and absence of the generic warning.
- Audited all repository Pydantic AI imports and API calls against the installed 2.13.0
  signatures/source and attempted a current-doc lookup. The Context7 connector was not
  available in this session, so the installed package was used as the exact runtime
  authority.
- Corrected handling of the full `ToolReturnPart.outcome` contract: only `success` now
  marks a Slack task complete and permits file upload; failed, denied, interrupted, and
  retry results are errors.
- Raised the declared Pydantic AI baseline from `>=1.107` to `>=2.13,<3` and refreshed
  the lockfile, matching the API generation the implementation and tests use.

## Why / decisions made
- `event.result` deterministically crashed after a successful review because that field
  does not exist on `FunctionToolResultEvent` in Pydantic AI 2.13.
- Treating denied or interrupted tool results as successful was inconsistent with the
  documented/runtime outcome union and could upload a stale or invalid artifact.
- An explicit 2.13 lower bound and pre-3 upper bound prevents environments from resolving
  an older incompatible API or silently crossing the next major-version boundary.
- The audit covered agents and generics, prompted output, OpenRouter model/settings,
  stream event types, result usage/history, message types, binary attachments, and
  Logfire instrumentation. No other incompatible or deprecated usage was found.

## Files touched
- `src/clanker/slack/stream.py` — modified — fixes event access and outcome semantics.
- `tests/test_slack_stream.py` — created — covers successful and interrupted tool results.
- `pyproject.toml` — modified — declares the Pydantic AI 2.13 API baseline.
- `uv.lock` — modified — refreshes the local package requirement metadata.
- `AI/journal/2026-07-19-11-slack-event-fix-and-pydantic-audit.md` — created — records
  this work.

## Open questions / for the human
- None blocking. The currently running bot process predates this edit and must be
  restarted before it loads the fix.

## Next steps
- Restart `clanker run`.
- Re-run the Slack review command and confirm the completed task, uploaded PDF, final
  assistant message, and saved conversation history.
