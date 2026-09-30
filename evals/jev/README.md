# Jev decision eval

An offline experiment: can TypeSafe's Jev (a typed-decision model, $0.042/M input tokens,
~1 s) make Clanker's review decision as well as the current DeepSeek agent does?

It replays **frozen production evidence** from Logfire, so later repo changes don't affect it,
and scores it against **the human Shipwright verdict on the same attempt** (read-only
Dashboard GETs). A project that was rejected, fixed, and later approved is scored per attempt,
so an older reject is never relabelled by a later approve.

Arms:
- `packet`: Jev sees only the deterministic pre-fetched packet plus facts computed in code.
- `agent`: packet plus the DeepSeek agent's tool calls/results (LLM investigates, Jev decides).
- baseline: DeepSeek's production verdict from the same trace.

Each Jev arm is scored two ways: `rules` (per-check answers combined in code, mirroring
`prompts/reviewer.md`) and `holistic` (one approve/reject Choice, with confidence gating to FLAG).

Run everything from the repo root. Data lands in `data/eval/jev/` (gitignored, contains
submission data).

```bash
# 1. needs LOGFIRE_READ_TOKEN (read token for floppy/clanker-v2) in .env
uv run python evals/jev/export_traces.py --per-verdict 60
# 2. human labels (read-only Dashboard, needs SHIPWRIGHTS_SESSION)
uv run python evals/jev/fetch_labels.py
# 3. Jev via OpenRouter (OPENROUTER_API_KEY); check the estimate first
uv run --with typesafe-sdk==0.7.2 python evals/jev/run_jev.py --dry-run
uv run --with typesafe-sdk==0.7.2 python evals/jev/run_jev.py --budget 0.30
# 4. report
uv run python evals/jev/report.py --gate 0.6
```
