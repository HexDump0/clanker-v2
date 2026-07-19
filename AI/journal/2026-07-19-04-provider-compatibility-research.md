# Provider compatibility and throughput research

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Compared current OpenRouter endpoints for DeepSeek V4 Flash, including advertised
  parameters, price, throughput, uptime, and observed tool/structured-output errors.
- Checked official Fireworks, Baidu, DeepSeek, Google Gemini, and OpenRouter
  documentation for reasoning, forced tool choice, and structured-output support.
- No implementation code or configuration was changed.

## Why / decisions made
- Fireworks is the strongest same-model smoke-test candidate: it advertises reasoning,
  tools, tool choice, and structured output for DeepSeek V4 Flash, documents forced
  tool selection and V4 reasoning controls, and OpenRouter currently reports roughly
  92 output tokens/s. Its recent uptime is comparatively poor, so it should not be the
  sole route without validation and fallback.
- Baidu is fast and reliable in current measurements, but its function-calling docs do
  not explicitly include DeepSeek V4 in the models supporting forced/named tool choice;
  it is not a safe assumption.
- Gemini 3.5 Flash on Google Vertex is the clearest high-throughput model/provider
  alternative: Google documents thinking, forced function calling, and structured
  output together for Gemini 3, while OpenRouter reports about 133–163 output tokens/s.
  It is substantially more expensive than DeepSeek V4 Flash.
- Endpoint metadata listing `reasoning`, `tools`, and `tool_choice` independently does
  not prove the combination `reasoning + tool_choice=required`; a minimal live smoke
  test is required before selecting a route.

## Files touched
- `AI/journal/2026-07-19-04-provider-compatibility-research.md` — created — records the
  provider recommendation and caveats.

## Open questions / for the human
- Is preserving DeepSeek V4 Flash's low price more important than guaranteed native
  structured-output compatibility?
- Is Fireworks' current uptime acceptable if OpenRouter fallbacks are enabled?

## Next steps
- Run one minimal compatibility request against Fireworks with reasoning plus a forced
  output tool before changing production routing.
- If it fails or reliability is unacceptable, evaluate Gemini 3.5 Flash with native
  structured output and review-level cost limits.
