# Review pipeline architecture and Alibaba failure research

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Developed a high-level architecture plan for watcher, Slack announcement, structured
  review, PDF generation, and isolated browser-video generation. No implementation
  code was changed.
- Researched current official Pydantic AI, OpenRouter, Alibaba Model Studio, and
  Playwright documentation.
- Correlated the documentation with Logfire trace
  `019f78826c6801a492f1d287f04e6fe1` and the installed Pydantic AI 2.13.0 behavior.

## Why / decisions made
- Recommend a durable application-controlled workflow rather than agents spawning
  agents. The review JSON is the canonical product; PDF and video are independent
  downstream artifact jobs. A video failure must not invalidate a completed review or
  PDF.
- Recommend splitting video creation into an optional planner that produces a validated
  scene plan and an isolated deterministic browser executor/recorder. The video worker
  consumes review evidence and does not reconsider the verdict.
- The Alibaba failure is a compatibility conflict: reasoning enables thinking mode;
  Pydantic AI's default structured output uses an output tool and requires forced tool
  choice; Alibaba thinking-mode function calling permits only `auto` or `none`.
- Preferred compatibility option to test is prompted JSON output with Pydantic
  validation while retaining thinking and ordinary tools on `auto`. Alternatives are
  disabling thinking while retaining tool output, or choosing a model/provider that
  supports forced tool choice with thinking. Merely requesting `tool_choice=auto` while
  retaining tool-only final output is not a complete fix.

## Files touched
- `AI/journal/2026-07-19-03-pipeline-architecture-and-alibaba-research.md` — created —
  records the requested plan and research.

## Open questions / for the human
- Should a video be generated for every review, or only rejects/warnings?
- Should partial success (review + PDF complete, video failed) be considered the normal
  completed state with a warning?
- Is SQLite-backed local durability sufficient initially, or does deployment require a
  separate queue/database from day one?

## Next steps
- Agree on the workflow/state model and canonical review/evidence schemas before code.
- Run a small provider compatibility matrix before choosing the structured-output fix.
