# Diagnosed Slack nested review failure

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Read the full `AI/README.md`, existing context, and journal history.
- Traced the Slack mention path from `app_mention` through the chat agent's
  `run_review` tool into `ReviewRunner` and the structured review agent.
- Queried Logfire trace `019f78826c6801a492f1d287f04e6fe1` read-only.
- Inspected the installed Pydantic AI 2.13.0 structured-output/tool-choice behavior.

## Why / decisions made
- The nested call is intentional in the current implementation: a general Slack chat
  agent uses `run_review` as a tool, and that tool invokes the separate structured
  review agent. It is not a framework-spawned sub-agent.
- The concrete failure was not caused by Shipwrights or packet fetching. All three
  dashboard GETs succeeded. The Alibaba provider rejected the structured review model
  request with HTTP 400 because thinking mode was enabled while Pydantic AI requested
  forced tool use (`tool_choice=required`/object).
- Pydantic AI uses tool-based structured output by default for this model profile;
  because plain text is not an allowed final result, it forces the output tool. The
  selected `deepseek/deepseek-v4-flash` Alibaba route does not accept forced tool choice
  in thinking mode.
- No implementation change was made because the human asked for an explanation and
  diagnosis, not a fix. Recommended direction: parse explicit Slack `review <URL|id>`
  commands deterministically and call `ReviewRunner` directly; keep a chat agent only
  for genuinely conversational requests. Independently, make review output compatible
  with the model/provider by disabling reasoning for tool-output mode, using prompted
  output, or selecting a compatible route/model.

## Files touched
- `AI/journal/2026-07-19-02-slack-nested-review-trace.md` — created — records this diagnosis.

## Open questions / for the human
- Should explicit Slack review commands bypass the chat agent entirely?
- For the formal reviewer, should reasoning be disabled, should output switch to
  prompted JSON, or should the configured model/provider be changed?

## Next steps
- If requested, implement the direct Slack review command route and add a regression
  test for URL/UUID extraction.
- Add a provider-compatible structured-output configuration and a focused model smoke
  test before the next live Slack run.
