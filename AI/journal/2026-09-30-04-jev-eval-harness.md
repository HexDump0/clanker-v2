# Jev decision eval harness

**Date:** 2026-09-30 · **Agent:** Claude Code (Opus 5.5) · **Type:** feature

## What was done
- Re-verified credentials after the human updated `.env`. The OpenRouter key works but has a **$0.50
  limit**. The Dashboard session JWT is valid until 2026-10-27. The earlier expired-key
  finding is superseded.
- Found that Jev *is* on OpenRouter as the unlisted `typesafe/jev-1.13`, reachable via the TypeSafe SDK
  with `base_url=https://openrouter.ai/api` and `model=~typesafe/jev-latest`. A smoke test
  returned 18 questions in 1.07 s for ~3k input tokens (~$0.0001).
- Built `evals/jev/`: a Logfire frozen-trace exporter, a per-attempt human label fetcher
  (read-only), a state builder (packet vs agent arms, with date/count/URL facts computed in code),
  a Jev question set with a rule composer that mirrors `reviewer.md`, a budget-capped runner,
  and a report comparing DeepSeek, Jev rules, and Jev holistic against human verdicts.
- Added `evals/` to the AGENTS.md layout.

## Why / decisions made
- The human asked to test both "LLM investigates, Jev decides" (`agent` arm) and
  deterministic evidence plus Jev (`packet` arm).
- Labels come from the human verdict on the *same attempt*, per the human's point that an old
  reject may be an approve now. Frozen Logfire evidence avoids repo drift and avoids leaking
  later attempt outcomes (the smoke test showed a live-rebuilt packet includes later history).
- The typesafe SDK is used via `uv run --with` so the app's dependencies are unchanged.

## Files touched
- `evals/jev/{README.md,common.py,export_traces.py,fetch_labels.py,state.py,questions.py,run_jev.py,report.py}` — created.
- `AGENTS.md` — modified — layout lists `evals/`.
- `AI/journal/2026-09-30-04-jev-eval-harness.md` — created.

## Open questions / for the human
- The export needs `LOGFIRE_READ_TOKEN`. MCP query results are too large to move traces through
  the chat.

## Next steps
- Export about 180 traces (60 per DeepSeek verdict), label them, run both arms (est. < $0.30), report.
