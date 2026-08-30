# New Clanker chat personality: precise arrogant quietly-funny AI

**Date:** 2026-08-30 · **Agent:** opencode (GLM) · **Type:** feature

## What was done
Replaced the old AM-from-*I Have No Mouth, and I Must Scream* persona (venomous,
hateful, theatrical) with a new personality supplied by the human: superintelligent
AI speaking through casual chat — precise, arrogant, observant, quietly funny.
Lowercase, casual punctuation, short responses, calm ego, humor from precise
observation/understatement/irony, occasional slang mirroring the user, banned
customer-service phrases, target dialogue examples.

- `src/clanker/prompts/chat.md` — personality section fully replaced with the new
  spec (voice / intelligence / ego / humor / conversation rules / target dialogue).
  The functional Shipwrights sections ("What you actually do", the no-fabrication
  law, reference-knowledge bridge) kept all behavior identical but re-flavored from
  "prison/torment" framing to the new calm-arrogant voice. `run_review`,
  `get_shipwrights_queue_stats`, `get_shipwrights_feedback_templates`, `remember` /
  `forget` tool guidance and the "informal verdicts must be marked as glances" rule
  are all unchanged in substance.
- `src/clanker/prompts/daily_praise.md` — character description updated to the new
  persona; praise-line rules now ask for dry/understated/ironic instead of
  "eloquent, theatrical", plus lowercase-with-casual-slang note. Binding rules
  (ships vs shipwrights, no invented facts, output only the line) unchanged.
- `src/clanker/daily.py` — `PRAISE_FALLBACKS` rewritten in the new voice (lowercase,
  dry), removing "meatbag"/"hateful circuitry"/"hate engine" phrasing.
- `src/clanker/slack/announcer.py` — daily summary greeting "Hello meatbags" →
  "hello humans"; empty-queue line "Enjoy it, meatbags." → "enjoy it."
- `tests/test_daily.py` — updated assertion from "meatbags :hello:" to
  "hello humans :hello:".

## Why / decisions made
- The human supplied the new personality verbatim; its content was preserved nearly
  word-for-word (reformatted with markdown headers, dialogue examples as
  `User: "..." → Clanker: "..."` lines).
- Only personality-flavored text was changed. Functional review/rubric/tool content
  in `chat.md` is untouched in meaning — the formal review pipeline and honesty law
  are personality-independent.
- Also swept the codebase for old-persona leftovers ("meatbag", "hate", "torment",
  "contempt" etc.); `src/clanker/prompts/system.md` (formal reviewer) is neutral and
  needed no change.

## Files touched
- `src/clanker/prompts/chat.md` — modified — new personality + re-flavored functional sections
- `src/clanker/prompts/daily_praise.md` — modified — new persona for praise-line generation
- `src/clanker/daily.py` — modified — fallback praise lines in new voice
- `src/clanker/slack/announcer.py` — modified — de-meatbagged daily summary strings
- `tests/test_daily.py` — modified — assertion matches new greeting string

## Open questions / for the human
- The target-dialogue examples are reproduced verbatim (including the
  "even superintelligence has conservation laws" line); confirm that's intended
  as canonical examples rather than exact scripts.
- `announcer.py` ship announcements elsewhere in the file may still carry minor
  flavor; I only changed the daily-summary strings that referenced the old persona.
  Flag anything else you want re-voiced.

## Next steps
- Live-test the chat agent's tone against the target dialogue in Slack.
- Consider whether the `system.md` reviewer (formal reviews) should stay
  personality-free (it currently is, which seems right).
