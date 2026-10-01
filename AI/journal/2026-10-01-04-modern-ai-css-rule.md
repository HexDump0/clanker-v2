# Code rule for modern AI CSS (ISO_VERSE miss)

**Date:** 2026-10-01 · **Agent:** Claude Code (Opus 5.5) · **Type:** feature

## What was done
- The human reviewed ISO_VERSE (`e86f1bc8…`) by hand: it passed the first layer with ai_code 0.67 (limit 0.7), but the CSS
  is clearly AI-generated. Diagnosis: Jev's AI-look criteria describe older AI tells. This CSS is the newer, comment-free
  GPT-5/Codex house style (noise grain, `.eyebrow`, `.reveal`, `letter-spacing: 0`, `--paper/--ink` tokens, ...).
- Measured 10 such signals on the 152 CSS-bearing eval reviews. The human chose a code rule over lowering
  the threshold or retraining Jev's question.
- `src/clanker/review/first_layer/ai_css.py`: the signals plus `REJECT_AT = 6`. `facts.add_evidence` computes
  `modern_ai_css_signals` from the CSS excerpts (kept out of Jev's state via `PRIVATE_FACTS`). `rules.code_rules`
  adds `ai_code` at 6 or more. Jev's `ai_code` no longer duplicates the reason. The reviewer adds a near-miss note at 4–5,
  and the PDF `ai_detection` row lists the signals.
- `evals/jev/state.py` computes the same fact. `report_v2.py` dev/holdout are unchanged (the rule never fires there; 0
  approved bounced). Added `evals/jev/ai_css_signals.py` (offline analysis).
- `tests/test_ai_css.py` (4 tests). `make_reviewer` in `tests/test_first_layer.py` accepts files. 195 tests pass.
- Live: ISO_VERSE now REJECTs with `ai_code` (9 signals). The message asks for the CSS to be rewritten by hand.
- Per the human, I committed the earlier work first (`613f146`).

## Files touched
- `src/clanker/review/first_layer/{ai_css.py (new),facts.py,rules.py,reviewer.py}`
- `evals/jev/{ai_css_signals.py (new),state.py}`, `tests/{test_ai_css.py (new),test_first_layer.py}`
- `AI/notes/modern-ai-css-rule-2026-10-01.md` (new): data, rationale, improvement ideas.

## Next steps
- See the note: validate on Oct+ labels, then teach Jev the modern style (re-run evals), use full files, add HTML/JS signals.
- The running bot needs a restart to pick this up.
