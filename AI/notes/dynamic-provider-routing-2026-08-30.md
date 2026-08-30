# Dynamic provider routing research

**Researched and implemented:** 2026-08-30

## Decision

Use the OpenRouter-compatible `provider` request object through both direct OpenRouter
and Hack Club AI. Do not name an upstream provider by default. The policy is:

```json
{
  "sort": "throughput",
  "preferred_max_latency": 2,
  "max_price": {"prompt": 0.5, "completion": 1.0},
  "require_parameters": true,
  "allow_fallbacks": true
}
```

Prices are USD per million tokens. `preferred_max_latency` is a soft p50 preference:
slower routes remain fallbacks rather than making the model unavailable. `max_price` is
a hard filter. The policy therefore chooses the fastest currently healthy compatible
route under a deliberately generous but bounded price ceiling without maintaining a
provider list in Clanker.

The thresholds are environment-configurable. An explicit provider allowlist remains an
escape hatch, but the deployed `.env` leaves both review and director allowlists empty.

## Why this is preferable

- OpenRouter calculates provider latency and throughput over a rolling five-minute
  window, so application-maintained rankings would become stale quickly.
- Sorting by throughput directly targets long review completion time. A latency sort
  would optimize time-to-first-token while potentially selecting slow token generation;
  default price load balancing would favor cost rather than wall time.
- A soft latency preference avoids endpoints with unreasonable startup delay while
  retaining recovery paths.
- A hard price cap prevents the throughput sort from selecting an arbitrarily expensive
  host.
- `require_parameters` matters for the review agent's tools and reasoning requests.
- The gateway can only select providers it actually exposes. This naturally handles the
  fact that Hack Club AI does not offer every OpenRouter provider.

## Live verification through Hack Club AI

- The unauthenticated model catalog currently includes both selected model IDs:
  `deepseek/deepseek-v4-flash-0731` and `qwen/qwen3.8-flash`.
- A minimal DeepSeek request containing the policy returned HTTP 200 in 0.89 seconds and
  reported `CoreWeave` as the selected upstream. This proves Hack Club AI passes provider
  preferences through and selects among its own available routes. No provider was named
  in the request.
- A valid 16x16 image request reached Qwen3.8 Flash on Alibaba. The first successful
  call spent its small 30-token limit entirely on default reasoning, so screenshot
  description now explicitly disables reasoning.
- Subsequent Qwen probes returned upstream shared-pool HTTP 429 responses. OpenRouter
  currently lists Alibaba as the model's only provider, so automatic failover is not
  possible for this model yet. More endpoints will automatically become candidates if
  exposed later.

No tokens, cookies, or API keys were recorded.

## Model facts relevant to the choice

- DeepSeek V4 Flash 0731 is the GA re-post-trained release, text-only, with roughly a
  1M-token context and tools/structured-output support. OpenRouter currently lists 29+
  providers.
- Qwen3.8 Flash is multimodal (text/image/video), with a 1M-token context and current
  list pricing around $0.15/M input and $0.47/M output. It currently has one provider.

## Sources

- https://openrouter.ai/docs/guides/routing/provider-selection
- https://openrouter.ai/deepseek/deepseek-v4-flash-0731
- https://openrouter.ai/qwen/qwen3.8-flash
- https://docs.ai.hackclub.com/api/get-models.html
- Live read-only `GET https://ai.hackclub.com/proxy/v1/models`
