# Chat bot: personality, full thread context, and simple memory

**Date:** 2026-07-19 · **Agent:** Claude (Fable 5) · **Type:** feature

## What was done

Gave the `@`-mention chat bot ("Clanker") a distinct personality and two new
capabilities, all **isolated from the review pipeline**.

1. **Personality prompt.** The chat agent no longer inherits the stage-by-stage
   reviewer instructions. It now uses a dedicated `prompts/chat.md` (an AM-inspired
   "Clanker" persona, human-authored) plus the rubric/pre-check/demo-guidelines
   appended as *reference* knowledge so it can still answer "what's allowed?"
   questions accurately and still trigger real reviews via `run_review`.

2. **Full thread context.** When mentioned in a thread, the bot now rebuilds its
   message history from the live Slack thread (`conversations.replies`) instead of
   only its own cached turns — so it sees messages posted before it was mentioned,
   across restarts. Falls back to the in-memory `ConversationStore` if the thread
   read fails (e.g. missing history scope).

3. **Simple long-term memory.** A tiny JSON-file-backed `MemoryStore` (flat
   `key -> fact`, size-capped, oldest-evicted) that Clanker manages itself via new
   `remember`/`forget` tools. Current memory is injected into the chat instructions
   as a dynamic instruction, so it's always fresh. Chat-only.

## Why / decisions made

- **Reviews must stay normal (explicit user requirement).** `create_review_agent`,
  `build_review_instructions()`, and the runner are untouched. Memory, thread fetch,
  and the remember/forget tools are wired **only** into `create_chat_agent`. The
  persona and memory prompts both explicitly forbid altering a formal verdict.
- **Thread as source of truth for history** (over the in-memory cache): gives true
  "whole thread" context and survives restarts. Consecutive same-role messages are
  merged and `<@Uxxx>` mentions + speakers are resolved to display names (cached via
  `NameResolver`) so multi-person threads read cleanly and memory can key on people.
- **Memory kept deliberately dumb:** flat map, model-managed, overwrite-by-key,
  capped at `chat_memory_max_entries` (default 200). No embeddings/retrieval — the
  user asked for "very simple."

## Files touched

- `src/clanker/prompts/chat.md` — created — Clanker persona + functional framing
  (rules Q&A, investigation, `run_review`, memory usage, "cruelty is theater, data is not").
- `src/clanker/review/agent.py` — modified — `build_chat_instructions()` (persona +
  rubric reference); `create_chat_agent()` gains `memory_provider` → dynamic
  instruction. Review agent unchanged.
- `src/clanker/slack/memory.py` — created — `MemoryStore` (load/flush/remember/forget/render).
- `src/clanker/slack/history.py` — modified — `NameResolver` + `fetch_thread_history()`.
- `src/clanker/slack/app.py` — modified — fetch thread history (fallback to cache),
  pass `context.bot_user_id`.
- `src/clanker/service.py` — modified — build `MemoryStore`, expose `remember`/`forget`
  tools, pass `memory_provider` to the chat agent.
- `src/clanker/config.py` — modified — `chat_memory_file`, `chat_memory_max_entries`.

## Open questions / for the human

- The AM persona is intentionally hostile toward real teen submitters. Confirm the
  tone is desired for the live channel before deploy; malice is easy to dial back in
  `chat.md` without touching wiring.
- Thread history needs the bot to have channel history scope
  (`channels:history`/`groups:history`). If absent, it silently falls back to the
  cache — verify the scope is granted in the Slack app config.
- Memory persists to `data/chat_memory.json` (gitignored data dir). No per-user
  namespacing — it's one global memory keyed by whatever keys the model picks.

## Next steps

- Consider a small pytest for `MemoryStore` and `fetch_thread_history` (currently
  only smoke-tested manually).
