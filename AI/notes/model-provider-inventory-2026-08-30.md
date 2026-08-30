# Model and provider inventory

> Updated later on 2026-08-30: the active choices are now DeepSeek V4 Flash 0731 and
> Qwen3.8 Flash with dynamic provider routing. See
> `AI/notes/dynamic-provider-routing-2026-08-30.md` for the implemented policy and live
> verification. The inventory below records the configuration before that change.

**Researched:** 2026-08-30

## Effective local configuration

The gitignored `.env` currently selects `AI_PROVIDER=hackclub`. Consequently every
model built by `clanker.llm.build_model` is sent to the OpenAI-compatible Hack Club AI
endpoint at `https://ai.hackclub.com/proxy/v1` using `HACKCLUB_API_KEY`.

| Workload | Model | Output / reasoning behavior |
|---|---|---|
| Formal certification review | `deepseek/deepseek-v4-flash` | Medium reasoning requested; tools; prompted and Pydantic-validated `ReviewOutput`; up to four retries |
| Slack mention chat | `deepseek/deepseek-v4-flash` | Medium reasoning requested; review/chat tools; plain text |
| Daily-summary praise line | `deepseek/deepseek-v4-flash` | Plain text; does not receive the review model settings, so no explicit reasoning effort |
| Rendered-page screenshot description | `qwen/qwen3-vl-8b-thinking` | Image + text to plain text; no explicit reasoning settings |
| Review-video direction | `nex-agi/nex-n2-mini` | Images + trusted findings; prompted and Pydantic-validated `VideoPlan`; up to two retries; exactly one successful model call intended |

The Qwen vision value is the code default because `.env` does not currently override
`VISION_MODEL_NAME`. The main and director model values are explicit `.env` overrides.

Exa web search is a separate optional review tool reached through
`https://ai.hackclub.com/proxy/v1/exa/search`; it is not one of the generative models
above. Browser capture, PDF rendering, video composition, and Shipwrights/GitHub data
fetches are deterministic application code rather than model calls.

## Provider-routing caveat

`.env` also contains:

- review provider `only=alibaba`, fallbacks disabled;
- director provider `only=nex-agi`, fallbacks disabled.

Those settings are **inactive** with `AI_PROVIDER=hackclub`. Both
`build_model_settings` and `build_director_model_settings` add the OpenRouter provider
object only when `AI_PROVIDER=openrouter`. The Hack Club proxy therefore chooses the
upstream route; the application does not currently enforce Alibaba or Nex AGI routing.
The actual upstream host cannot be established from configuration alone.

## Current external facts

- Hack Club AI documents an OpenRouter/OpenAI-compatible proxy and a live unauthenticated
  model catalog. Its catalog currently lists all three configured model IDs and reports
  tools, tool choice, reasoning, response formats, and structured outputs among their
  supported parameters.
- Hack Club AI documents a per-user limit of 450 chat-completion/embedding requests per
  30 minutes.
- OpenRouter describes DeepSeek V4 Flash 0423 as a 1M-context, efficiency-focused
  reasoning/coding/agent model. The unversioned slug used by Clanker currently names
  that 0423 release, not the newer `deepseek-v4-flash-latest` alias.
- OpenRouter describes Nex-N2-Mini as a 262K-context multimodal agentic model. Current
  displayed endpoint performance is about 33 output tokens/s with roughly 0.60 s
  initial latency.
- OpenRouter describes Qwen3-VL-8B-Thinking as a multimodal reasoning model. Its current
  performance page shows Alibaba as its sole route, about 120 output tokens/s, and no
  prompt-cache hits in the displayed recent measurements.

Sources:

- https://docs.ai.hackclub.com/
- https://docs.ai.hackclub.com/api/get-models.html
- https://docs.ai.hackclub.com/guide/rules.html
- https://openrouter.ai/deepseek/deepseek-v4-flash/api
- https://openrouter.ai/nex-agi/nex-n2-mini
- https://openrouter.ai/qwen/qwen3-vl-8b-thinking/performance
- https://openrouter.ai/docs/guides/routing/provider-selection

## Speed implications to investigate next

1. Benchmark the real review path through Hack Club AI versus direct OpenRouter routes;
   the current provider pins do not affect Hack Club requests.
2. Replace or benchmark the Thinking Qwen model for screenshot description, a bounded
   factual task that likely does not need extended reasoning.
3. Use a small fast text model for the one-sentence daily praise call rather than the
   full review model.
4. Capture actual model/provider/timing metadata per workload before switching models.
   Current code records director token usage, while the architecture calls for broader
   request metadata; configuration alone cannot reveal the proxy's selected upstream.
5. Continue reducing review tool rounds and large file payloads. Earlier trace analysis
   found 64 seconds, six rounds, and 115,270 input tokens for one review; packet
   enrichment was subsequently expected to cut this to about three rounds, but that
   needs a fresh measured trace.
