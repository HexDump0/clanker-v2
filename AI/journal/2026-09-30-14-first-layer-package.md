# First-layer review package (partial wiring)

**Date:** 2026-09-30 · **Agent:** Claude Code (Opus 5.5) · **Type:** feature

## What was done
- Added the `typesafe-sdk` dependency. New settings: `review_mode` (default first_layer),
  `jev_model` (pinned to `typesafe/jev-1.13`, verified via OpenRouter), `jev_timeout`, `banner_model_name`.
- New `src/clanker/review/first_layer/`: `facts.py` (packet parser + code facts), `rules.py`
  (Jev questions, code rules, thresholds, decision), `evidence.py` (pinned code excerpts, release
  assets, banner label), and `reviewer.py`. `FirstLayerReviewer.review(packet)` returns a result with the
  verdict, reasons, message and video inputs. `to_review_output` maps it into the existing ReviewOutput
  shape for Slack/PDF/CLI.
- The eval harness now imports this production logic. Parity is confirmed: holdout 98 rejects / 89% /
  61% / 11 bounced; dev 61 / 89% / 7 bounced (unchanged).

## Not done yet (next steps)
- `ReviewRunner` + `service.build_app` still use the DeepSeek agent. Next: when `review_mode ==
  first_layer`, call `FirstLayerReviewer`, then `to_review_output`, the PDF, and on REJECT
  `generate_reject_video`; add `reject_message` to `ReviewOutcome` and post it in the Slack thread.
- Tests for `first_layer/reviewer.py` (fake Jev asker) and the runner path.
- The local `.env` still has `AI_PROVIDER=hackclub` and `VIDEO_ENABLED=false`.
