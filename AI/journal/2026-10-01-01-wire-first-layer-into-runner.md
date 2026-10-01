# Wire the first-layer reviewer into ReviewRunner, build_app and Slack

**Date:** 2026-10-01 · **Agent:** Claude Code (Opus 5.5) · **Type:** feature

## What was done
- Continued from `2026-09-30-14` (first-layer package built, not wired).
- `ReviewRunner` now accepts either `first_layer=FirstLayerReviewer` or `agent=` (at least one is
  required, and the first layer wins if both are given). The first-layer path is packet → `FirstLayerReviewer.review`
  → `to_review_output` → PDF, and on REJECT with `VIDEO_ENABLED` → `generate_reject_video(seed=cert_id)`.
  PDF rendering and the timeout/failure-isolated video stage are shared helpers used by both paths.
  The agent path behaves as before.
- `ReviewOutcome` gained `reject_message` and `first_layer` (the raw `FirstLayerResult`).
  The token counts for first-layer outcomes are Jev input tokens in / 0 out.
- `service.build_app` builds only the reviewer for `REVIEW_MODE`. In first_layer mode, no DeepSeek review
  agent or VisionDirector is constructed. The chat `run_review` tool JSON includes `reject_message`.
- Slack `post_outcome`: when there is a reject message, it is posted in the thread as
  "Reject message:" plus a code block (copy-ready, for a human to send from the dashboard; no mutating
  calls), after the reject ping and before the PDF/video.
- CLI `clanker review` prints the reject message.
- Tests: `tests/test_first_layer.py` (8 tests covering the reviewer with fake Jev/evidence, PASS/REJECT, the code-rule reject,
  the key requirement, runner REJECT → message/PDF/video, PASS → no video, a video failure that keeps the verdict, and the
  constructor guard), plus an announcer test for the reject message. `uv run pytest -q`: 138 passed.
  `ruff check src tests` passes cleanly. `ruff format` was already not applied to the touched files, so I did not reformat them.
- Live smoke test (one cert, read-only Dashboard GETs, OpenRouter cost < $0.01, Logfire disabled, outputs in the
  session scratchpad): `AI_PROVIDER=openrouter VIDEO_ENABLED=true uv run clanker review
  4fad71aa-…`. Result: REJECT `readme_not_raw` + `ai_readme`, a message, a PDF, and a 19 s / 1.2 MB video. 40 s end to end
  (packet ~5 s, evidence+banner ~5 s, Jev 0.75 s, video ~30 s).

## Why / decisions made
- The reviewer is selected by the presence of the injected object, not by reading settings inside the runner. That way
  `build_app` is the one place that decides, and the existing agent-path test kept working unchanged.
- The reject message goes to Slack rather than to the dashboard: Clanker stays advisory and never calls
  `[MUTATING]` endpoints.

## Observation (not acted on)
- In the smoke cert, `ai_readme` fired on a README that reads as the author's own voice ("one of my first
  programming projects…", "the stopwatch has a slight delay"). The human rejected only for the raw link.
  This is a likely false positive. Worth tracking once live rejects accumulate.

## Files touched
- `src/clanker/review/runner.py`, `src/clanker/service.py`, `src/clanker/slack/announcer.py`,
  `src/clanker/cli.py` — modified.
- `tests/test_first_layer.py` — created. `tests/test_announcer.py` — modified.
- `.env.example`, `README.md`, `AI/context/v2-architecture-plan.md` — documented `REVIEW_MODE`.

## Open questions / for the human
- The local `.env` still has `AI_PROVIDER=hackclub` (dead) and `VIDEO_ENABLED=false`. Production needs
  `AI_PROVIDER=openrouter`. Should reject videos be on?
- The OpenRouter key had a $0.50 limit (per `2026-09-30-04`). The first layer is well under a cent per review
  (Jev ~7k input tokens, plus the banner and demo vision calls on a $0.02/M model), but at about 134 reviews/day that
  limit still won't last long. Not measured precisely.
- Nothing is committed yet (branch `jev-first-layer-eval`).

## Next steps
- Deploy with `REVIEW_MODE=first_layer`, then compare live REJECTs against human outcomes for a week.
- The ReviewJob/SQLite durable-state work from the architecture plan is still unstarted.
