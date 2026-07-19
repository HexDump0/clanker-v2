# Non-Fireworks provider compatibility probes

**Date:** 2026-07-19 · **Agent:** Codex (GPT-5) · **Type:** research

## What was done
- Tested OpenRouter routes for DeepSeek V4 Flash with the exact feature combination that
  crashes on Alibaba: reasoning enabled, a function tool, and `tool_choice=required`.
- Used a small synthetic arithmetic task and verified both the selected provider and the
  returned tool arguments. No real review or mutating Shipwrights API was invoked.
- Compared Morph, SiliconFlow, Novita, Baidu, DeepSeek, and AtlasCloud. No secret was
  printed or stored.

## Why / decisions made
- Morph, SiliconFlow, and Novita all returned HTTP 200 and correctly called the required
  result tool. Morph and SiliconFlow also returned non-zero reasoning-token evidence.
- Novita made the correct call but reported zero reasoning tokens, so it is a weaker fit
  when preserving thinking is important.
- Baidu correctly called the required tool but returned no visible reasoning and zero
  reasoning tokens across probes.
- The DeepSeek route returned 404 for this model and AtlasCloud returned 400 for the
  tested combination.
- Of the tested same-model, non-Fireworks options, SiliconFlow and Morph are the clearest
  compatibility matches. Provider substitution only avoids the Alibaba restriction; a
  prompted JSON output mode remains the provider-independent fix.

## Files touched
- `AI/journal/2026-07-19-07-non-fireworks-provider-probes.md` — created — records
  sanitized live compatibility findings.

## Open questions / for the human
- Prefer SiliconFlow's stronger recent uptime or Morph as the primary route?
- Keep Alibaba by changing the review's final output mode, or pin a compatible provider?

## Next steps
- Rotate the OpenRouter key that was pasted into chat.
- If changing providers, run a real read-only review in staging before production use.
- Add bounded retry and a compatible fallback for transient upstream failures.
