# Rule fixes after manually reviewing wrong rejects

**Date:** 2026-09-30 · **Agent:** Claude Code (Opus 5.5) · **Type:** fix

## What was done
- Hand-checked all 24 v2 rejects of human-approved attempts (14 holdout, 10 dev) using README, tree,
  code excerpts, demo render, human comment, and the banner images.
  Findings: Clanker was wrong on 10 (3 no_source from unknown extensions like .pyw/.luau, 5 banner
  mislabels of site-header crops, 2 demo_broken on a Unity loading screen and a Cloudflare 403). Reviewers
  were lenient or missed the issue on 11 (thin READMEs, a non-raw README link, strong AI-code signs).
  3 were timing mismatches or judgment calls.
- Fixed per the human's choice. The banner check stays as is ("general automation inaccuracy").
  - no_source: now requires zero GitHub language bytes (from the packet), not just unknown extensions.
  - demo_broken: skipped on bot-wall/challenge pages (Cloudflare, 403/429) and on game-engine loading screens.
  - needs_api_key: skipped for bots whose demo is a live Slack/Discord/Telegram channel.
  - itch_no_build: counts browser-embedded builds (fullscreen/loading/embed/canvas) as playable.
- Also fixed two lint issues in eval scripts: an unused import, and a loop-bound lambda in messages.py.
- Holdout v2 after the fixes: 98 rejects at 89% precision, catching 61% of human rejects, with 11/43 good projects bounced
  (before: 107, 87%, 65%, 14/43; DeepSeek: 68, 87%, 41%, 9/43).
  Dev: 61 rejects at 89%, 7/26 bounced (before: 66, 85%, 10/26).
- `uv run pytest -q` gives 124 passed. Ruff (src/tests plus evals E,F,B) is clean.

## Files touched
- `evals/jev/state.py`, `evals/jev/questions_reject.py`, `evals/jev/evidence.py`, `evals/jev/messages.py`.

## Next steps
- Wire the first-layer path into production.
