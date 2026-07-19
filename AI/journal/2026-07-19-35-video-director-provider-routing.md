# Separate video director provider routing

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** fix

## What was done
- Diagnosed video director failure trace `019f7a8f7cf78572c27053f2cb39e3f5` as an
  OpenRouter provider conflict: `nex-agi/nex-n2-mini` was inheriting the review agent's
  `alibaba`-only provider restriction even though the model is available from `nex-agi`.
- Added independent video-director provider and fallback settings.
- Changed director model settings to use only its own provider pins and never inherit the
  review agent's pins.
- Configured the local director provider as `nex-agi` and documented the new environment
  variables in `.env.example`.
- Added regression tests for explicit director routing and for the no-inheritance default.

## Why / decisions made
- Review and video direction use separate models, so their provider availability can
  differ. Model routing must follow the same boundary.
- An empty director provider setting permits free OpenRouter routing; it does not fall
  back to the review provider setting.

## Files touched
- `src/clanker/config.py` — modified — added director provider settings and parsed pins.
- `src/clanker/review/video/director.py` — modified — isolated director model routing.
- `.env.example` — modified — documented the new environment variables.
- `.env` — modified locally — pinned the configured Nex director model to `nex-agi`.
- `tests/test_video.py` — modified — added provider-routing regressions.
- `AI/context/v2-architecture-plan.md` — modified — recorded independent routing boundary.

## Open questions / for the human
- None.

## Next steps
- Restart `uv run clanker run` so the process loads the new settings, then retry the
  review and confirm the director call proceeds to video encoding and Slack upload.
