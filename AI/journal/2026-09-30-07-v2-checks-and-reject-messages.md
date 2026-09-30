# v2 first-layer checks + human-style reject messages

**Date:** 2026-09-30 · **Agent:** Claude Code (Opus 5.5) · **Type:** feature

## What was done
- Committed the earlier eval work on branch `jev-first-layer-eval` (9e2e10b). The human asked to
  branch/commit, and I created the branch per the rule about not committing directly to main.
- v2 checks (`evals/jev/evidence2.py`, `questions_reject.py`, `state.py`, `report_v2.py`,
  `thresholds_conservative2.json`):
  - banner: default banner via a code rule, otherwise a free vision label from Space Bunny;
  - code demo checks: video, repo link, missing release build, itch without a build, bot link;
  - cheap checks: no source, untitled, Jev needs_api_key; demo_broken switched on;
  - #6: code excerpts chosen by real file size at the submission commit, head plus a middle slice.
  The "README lacks demo link" check was deliberately not built, per the human.
- The holdout was extended to 186 labelled reviews. Results were appended to `AI/notes/jev-eval-results-2026-09-30.md`.
- Built `src/clanker/review/reject_message.py` (no-LLM, Shipwright-style reject text) with
  `tests/test_reject_message.py` (26 tests), plus `evals/jev/messages.py` to produce sample messages.
- `uv run ruff check src tests` passes cleanly. `uv run pytest -q` gives 123 passed.

## Why / decisions made
- The human wants reject reasons that are not AI-written and don't read as AI. I chose templates mined
  from real reviewer comments over any model, which makes the output deterministic and auditable.
- The message never names a real reviewer and never claims someone tested the project (e.g. "when I tried"),
  so its content stays truthful.

## Files touched
- `src/clanker/review/reject_message.py`, `tests/test_reject_message.py` — created.
- `evals/jev/{evidence2.py,report_v2.py,messages.py,thresholds_conservative2.json}` — created.
- `evals/jev/{questions_reject.py,state.py,run_jev.py,README.md}` — modified.
- `AI/notes/jev-eval-results-2026-09-30.md` — appended.

## Open questions / for the human
- Drop `no_source` (50% precision)? Keep the banner check (95% holdout, 64% dev)?
- Not yet committed: the human said they'll separate the Jev v2 work and the reject-message work themselves.

## Next steps
- Wire the first-layer path into `ReviewRunner`: code facts, one Jev call, then REJECT with a message or PASS.
