# Browser render + vision describer for demo pages

**Date:** 2026-07-19 · **Agent:** Claude (Fable 5) · **Type:** feature

## What was done

Gave the review pipeline eyes — a one-shot "does this look right?" render, not a
browser agent:

- **`review/browser.py`** (new): `render_page(url)` loads the page in headless
  Playwright Chromium (fresh incognito context, 1280×800, no cookies/credentials,
  downloads refused, hard timeout, `networkidle` grace ≤5s) and returns final
  URL, status, post-JS visible text (20k cap), a `viewport_mostly_empty` flag
  (<40 visible chars), and a JPEG screenshot. Errors are data, never raised.
- **`review/vision.py`** (new): a describer agent on `qwen/qwen3-vl-8b-thinking`
  (`VISION_MODEL_NAME` setting) with a deliberately general prompt: describe the
  screenshot in detail — layout, text, UI elements, blank areas, error messages,
  overlays — **describe, don't judge**. The human explicitly wants judgment to
  stay with the review agent (which has full submission context) and the vision
  output to be evidence only, with no cap on the description passed through.
  `PageRenderer` combines render + describe into one JSON payload. Per the
  human: console logs and failed-request counts are NOT collected/surfaced —
  deemed not useful to the agent.
- **`review/tools.py`**: new `review_render_page(url)` tool (renderer injected,
  optional — returns a clear error when rendering is disabled/unavailable).
- **`review/packet.py`**: if the cert has a demo URL, the packet pre-renders it
  concurrently with the other enrichment ("Demo page render (pre-fetched)"
  section: final URL/status, empty-viewport flag, uncapped vision description,
  rendered text). Failed renders are skipped (not evidence either way).
- **`clanker/llm.py`** (new): `build_model(settings, model_name=None)` moved out
  of `review/agent.py` so vision can build models without an import cycle
  (agent → tools → vision → agent).
- **Config**: `browser_render_enabled` (default true), `vision_model_name`
  (default `qwen/qwen3-vl-8b-thinking`), `render_timeout` (20s).
- **Deploy**: `playwright` dependency; Dockerfile runs
  `playwright install --with-deps chromium`; README setup updated.
- **`prompts/system.md`**: packet section + tool bullet ("look, don't crawl";
  the description reports what's visible, judging it is the agent's job).

## Why / decisions made

- Vision model = describer, not judge — the human rejected a
  looks_like-verdict schema; the vision model lacks submission context and its
  confident misreads would propagate. Chose Qwen3-VL over cheaper MiMo-V2.5 for
  GUI/OCR strength; `-thinking` variant per the human's pick (~$0.12/$0.46 per M
  on OpenRouter, ≈$0.001/review).
- One-shot render (no click/type/navigate loop) keeps cost and flakiness
  bounded; isolation follows the v2 architecture plan's browser rules.

## Verification

- 36 tests pass (5 new: invalid URL, tool-without-renderer error, PageRenderer
  payload with TestModel, packet demo-render section, real-Chromium render
  against a local socket server — skips when Chromium missing). Ruff clean.
- Live smoke test: rendered https://example.com, got a detailed factual
  description back from qwen3-vl-8b-thinking via OpenRouter. Works end to end.

## Files touched

- `src/clanker/review/browser.py` — created
- `src/clanker/review/vision.py` — created
- `src/clanker/llm.py` — created (build_model moved from review/agent.py)
- `src/clanker/review/{tools,packet,agent}.py`, `src/clanker/service.py`,
  `src/clanker/config.py`, `src/clanker/prompts/system.md` — modified
- `pyproject.toml`, `uv.lock`, `Dockerfile`, `README.md` — modified
- `tests/test_review.py` — modified (5 new tests)

## Next steps

- Watch a live review in Logfire: confirm the demo-render section actually
  reduces demo-probing tool rounds and the description quality holds on real
  ships (CSR apps especially).
- Later (per architecture plan): move rendering to a separately supervised
  worker process if browser crashes ever destabilize the service.
