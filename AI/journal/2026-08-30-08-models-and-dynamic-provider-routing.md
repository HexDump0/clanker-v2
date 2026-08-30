# Models and dynamic provider routing

**Date:** 2026-08-30 · **Agent:** Codex (GPT-5) · **Type:** feature

## What was done
- Set the default/main reasoning model to `deepseek/deepseek-v4-flash-0731` and the
  screenshot vision model to `qwen/qwen3.8-flash` in code, `.env.example`, and the local
  gitignored `.env`.
- Removed deployed provider pins and enabled one shared dynamic provider policy across
  formal reviews, Slack chat, screenshot vision, daily praise, and the optional director.
- Configured throughput sorting, a soft two-second p50 latency preference, $0.50/M input
  and $1.00/M output ceilings, parameter compatibility, and automatic fallbacks.
- Disabled reasoning for screenshot description because Qwen3.8 Flash enables it by
  default and this workload needs fast factual perception rather than deliberation.
- Researched official routing/model documentation, queried the live Hack Club model
  catalog, and ran sanitized minimal provider and vision probes.
- Added and updated routing/default-model regression tests.

## Why / decisions made
- Provider performance changes continuously, so OpenRouter-compatible rolling routing
  data is a better source than a hardcoded provider name or application-maintained list.
- The Hack Club proxy accepted the complete provider object and dynamically selected
  CoreWeave for the DeepSeek probe, confirming the policy works through the configured
  gateway and only considers routes Hack Club exposes.
- Qwen3.8 Flash currently has only Alibaba. Live vision routing reached Alibaba, but its
  shared pool subsequently returned 429; no provider policy can create a fallback that
  the model catalog does not offer.
- Kept explicit allowlists as an emergency override, but cleared them in the active
  configuration.

## Files touched
- `src/clanker/config.py` — modified — current model defaults and configurable dynamic
  routing thresholds.
- `src/clanker/llm.py` — modified — shared provider policy for direct and proxied calls.
- `src/clanker/review/agent.py` — modified — review/chat use shared routing.
- `src/clanker/review/vision.py` — modified — shared routing and no-reasoning vision.
- `src/clanker/review/video/director.py` — modified — dynamic policy when unpinned.
- `src/clanker/daily.py` — modified — daily praise uses shared routing.
- `.env.example` — modified — documents model and dynamic routing configuration.
- `.env` — modified locally — selects models and clears provider pins; remains ignored.
- `tests/test_review.py` — modified — model, proxy-routing, pin-override, and vision tests.
- `tests/test_video.py` — modified — director dynamic-routing expectation.
- `AI/context/v2-architecture-plan.md` — modified — records the default policy.
- `AI/notes/dynamic-provider-routing-2026-08-30.md` — created — research and live results.
- `AI/journal/2026-08-30-08-models-and-dynamic-provider-routing.md` — created — this entry.

## Open questions / for the human
- Qwen3.8 Flash's only current upstream is intermittently rate-limited. Keep it with
  graceful missing descriptions, or configure a fallback *vision model* (not provider)?

## Next steps
- Restart the running Clanker service so it loads the updated `.env` and code.
- Measure a real review trace to tune the latency and price thresholds from production
  evidence rather than the conservative starting values.

## Verification
- `uv run pytest -q` — 96 passed.
- `uv run ruff check src tests` — clean.
- `git diff --check` — clean.
- Minimal Hack Club DeepSeek dynamic-routing probe — HTTP 200; automatically selected
  CoreWeave; 0.89 s total.
- Minimal Qwen image probe — reached Alibaba and succeeded once; later probes exposed an
  upstream shared-pool 429 limitation.
