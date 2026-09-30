# Context build for speed/cost optimization discussion

**Date:** 2026-09-30 · **Agent:** Claude Code (Opus 5.5) · **Type:** research

## What was done
- Read `AI/README.md`, all `AI/context/` files, the model/provider and dynamic-routing
  notes, and the cost-relevant journals (07-19-16/17/18, 08-29-01, 08-30-05..12, 08-31-*).
- Read the review pipeline (`llm.py`, `review/agent.py`, `runner.py`, `packet.py`,
  `vision.py`, `browser.py`, tool registration in `tools.py`), `service.py`,
  `slack/app.py`, the director, and the non-secret model/routing keys in `.env`.
- No code or config changed. No Logfire queries (the Logfire MCP needs interactive auth).

## Findings (the speed/cost lever map, unmeasured)
- Active models: DeepSeek V4 Flash 0731 for review, chat and daily praise
  (`REASONING_EFFORT=medium` for review *and* chat); Qwen3.8 Flash (no reasoning) for
  screenshots. `VIDEO_ENABLED=false`, so the director model is not used. All traffic goes
  through the Hack Club AI proxy with `sort=throughput`, allow_fallbacks, and price caps.
- The last measured review (07-19, before packet enrichment and the current model) cost
  about $0.006 and took 64 s over 6 rounds with 115k input tokens. Rounds and latency
  drive this more than the per-token price does. No newer trace has been analysed.
- Review static prefix: about 35.5k chars of instructions (about 9k tokens) plus 15 tool
  schemas. The packet can be large: README up to 30k chars, a tree of up to 500 paths,
  rendered text up to 20k chars, an uncapped vision description, and up to 50 devlogs of
  700 chars each. The whole packet is replayed on every tool round.
- `get_github_file_content` still truncates at 50k chars. Item 4/5 from 07-19-16
  (`max_chars`, gating releases by project type) was never done.
- Packet build blocks on the slowest enrichment. The demo render (fresh Chromium launch,
  up to 20 s load and 5 s networkidle, then a serial vision call) is probably on the
  critical path.
- Chat: about 38.5k chars of instructions (about 10k tokens), with medium reasoning on
  every message, including debounced auto-follow messages in watched threads.
- Unverified risk: throughput sorting with fallbacks may move consecutive rounds of one
  run to different upstreams, which would defeat the implicit prefix caching that 07-19-16
  observed. This needs a check of the provider metadata in the traces.

## Files touched
- `AI/journal/2026-09-30-01-speed-cost-context-build.md` — created — this entry.

## Open questions / for the human
- Which target matters: review wall time, chat reply latency, dollar cost, or Hack Club
  AI rate-limit headroom? Does the Hack Club proxy actually bill this account?
- May an agent query production Logfire (this needs auth) to get current per-stage timings,
  rounds, tokens, upstream providers, and validation-retry rates?

## Next steps
- Pull 10–20 recent review traces and a sample of chat traces to build a real baseline
  before changing anything.
