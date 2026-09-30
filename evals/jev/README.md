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

## First-layer (confident reject) flow

Clanker is the automated first layer. It only REJECTs what it can confidently establish;
everything else passes to a human. Splits are selected with `JEV_DATASET=dev|holdout`
(export the holdout with `--random N` so it follows the production mix).

```bash
export JEV_DATASET=holdout
uv run python evals/jev/evidence2.py        # pinned code excerpts, release assets, banner label (free vision)
uv run --with typesafe-sdk==0.7.2 python evals/jev/run_jev.py --arms reject,reject2
uv run --with typesafe-sdk==0.7.2 python evals/jev/report_v2.py   # v1 vs v2 + decisions_v2.csv
```

v2 adds code checks: default or bad banner (vision label), demo is a video, demo is the repo,
missing release build (desktop/Android/CLI), itch.io page without a build, bot link that isn't
an invite/channel, no source, "untitled". It adds Jev `project_type` and `needs_api_key`, turns
on `demo_broken`, and picks code excerpts by real file size (largest style/UI/logic file, head
plus a middle slice). Thresholds are in `thresholds_conservative2.json`.
