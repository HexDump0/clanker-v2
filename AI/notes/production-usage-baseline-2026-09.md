# Production usage baseline (Logfire, 2026-08-31 → 2026-09-25)

Source: Logfire project `floppy/clanker-v2`. Retention starts at 2026-08-31. Production
stopped on 2026-09-25 after Hack Club AI access ended because usage was too heavy. All
traffic went through `ai.hackclub.com` using dynamic `sort=throughput` routing. Most figures
below cover 2026-09-12 → 09-26 unless another window is stated.

## Volume
- Reviews: **~134 distinct certs/day**, almost always one review each (1,865 certs reviewed
  once and 10 twice in 14 days). The watcher reviews every new ship.
- Chat agent: effectively unused (16 runs in the first two weeks, 0 afterwards). Daily
  praise: 1/day.
- LLM requests: about 470 DeepSeek and 170 Qwen requests per day. That is about 10M review
  input tokens per day.

## Review agent (DeepSeek V4 Flash 0731, reasoning=medium)
| metric | value |
|---|---|
| wall time (agent only) | p50 35–41 s, p90 91–94 s |
| rounds | avg 3.5, p50 3, p90 6, max 25 |
| tool calls | avg 4.9 per review |
| input tokens | p50 63k, p90 159k, max 1.57M; avg 81–96k |
| cache-read share of input | ~67% overall; **only ~33% on round 1**, 77–97% on later rounds |
| output tokens | avg ~5.4k per review, **~66% of them reasoning** |
| round-1 prompt | avg ~17.9k tokens (instructions + tool schemas + packet) |
| per-round latency | ~9 s avg per model request |

- Long tail: the 103 reviews above 200k input tokens (5.7%) used **21%** of all review input.
  One run hit the 50-request limit after using 2.49M tokens.
- Verdict mix: APPROVE 806, REJECT 614 (24 of them instant-reject), FLAG_FOR_HUMAN 372 (21%).
  Flagged reviews are the most expensive, averaging 128k input tokens and 76 s.
- Errors (09-12 → 26): 81 were 402 insufficient credits (the proxy budget ran out), 5 hit
  max output retries, 5 were 502/504 gateway errors, and 1 was a timeout that took 391 s.
  The OpenAI client's default `max_retries=2` stretches the 120 s `agent_timeout` to about 6 minutes.

### Tool calls (14 days, ~1,875 reviews)
get_github_file_content 2292 · **get_github_repo_info 1804 (~1 per review)** ·
get_github_commits 1073 · check_url 774 · get_github_readme 577 · **render_page 538
(avg 14.6 s)** · get_github_releases 503 · get_github_repo_tree 345 · fetch_page_text 303 ·
fetch_stardance_project 228 · others < 100.
The packet already carries commits, README, tree, and the Stardance page, so many of these
calls repeat data the agent already has.

## Vision describer (Qwen3.8 Flash, no reasoning)
- About 1 call per review from the packet pre-render, plus render_page tool calls.
- Successful calls: p50 9.7 s, p90 17 s, about 680 output tokens.
- Failures: 429s took about 34 s each (68 calls), 5 timeouts took about 362 s each, and there were 82 402s.
- Vision runs inside `build_packet`, before the review agent starts, so it sits directly on
  the critical path.

## Price context (OpenRouter endpoints for deepseek-v4-flash-0731, fetched 2026-09-30)
Providers differ by roughly 40× on input price. Examples in USD per 1M tokens (input / output / cache read):
DeepInfra 0.06/0.18/0.015 · CoreWeave 0.13/0.28/0.07 · Together 0.14/0.28/0.03 ·
Alibaba 0.35/1.06/0.035 · Cloudflare 0.44/1.32/0.014. The old caps ($0.5 input / $1.0 output) still allowed
most of these. Rough review cost is ~$0.009 at CoreWeave prices and ~$0.0034 at DeepInfra
prices. At 134 reviews/day that is about **$14–36/month** for reviews, and vision costs very little.

## Observability gaps
- `review_cert` has no enclosing span. The review agent span is a trace root, so packet build
  time (render + vision + fetches) cannot be read directly from Logfire.
- The upstream provider chosen per request is not recorded.
