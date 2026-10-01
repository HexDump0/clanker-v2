# Modern AI CSS code rule (2026-10-01)

**Status:** live in the first layer as a stop-gap. The human asked to keep this here so it can be
revisited and improved later.

## Why it exists
- Ship **ISO_VERSE** (`e86f1bc8-a80b-4b54-a43f-79b1ab236542`, Oct 1) passed the first layer with Jev
  `ai_code` = 0.67 (limit 0.7). The human reviewed it by hand: the styling is clearly AI-generated.
- Jev's `ai_code` criteria (`rules.py`, `AI_LOOK`) describe *older* AI tells: gradient hero sections,
  glassmorphism, `/* ===== Section ===== */` banners, emoji comments. Newer (GPT-5/Codex-era) CSS
  has **no comments at all** and a different, very consistent house style:
  - an "editorial" token palette: `--paper`, `--ink`, `--muted`, `--line`, `--surface`, …
  - an SVG `feTurbulence`/`fractalNoise` grain overlay on `body::before`
  - `.eyebrow` (or `.kicker`/`.overline`) labels in uppercase mono, often with a line `::before`
  - `letter-spacing: 0` (explicitly zero)
  - `.shell { width: min(var(--page-width), calc(100% - 64px)) }`
  - logical properties: `margin-inline`, `padding-block`, `inset: 0`
  - `.reveal` / `.reveal.is-visible` scroll animations and `@keyframes arrive`
  - stock fonts: DM Sans / DM Mono / Manrope / Space Grotesk / Inter / Fraunces / Instrument Serif
  - `color-scheme: light`, `clamp()` type scales
  - (not counted) CSS indented 8 spaces, i.e. lifted out of a single-file HTML `<style>` block

## The rule
- `src/clanker/review/first_layer/ai_css.py`: 10 signals (9 regexes plus "4 or more stock-named tokens").
  They are counted on the **CSS excerpts** the evidence step already fetches (head 2,500 plus a middle
  1,500 chars of the largest stylesheet).
- At **6 or more signals**, the code rule adds `ai_code` (reject), whatever Jev says. At 4–5 signals, it adds a near-miss note for the human
  reviewer. The PDF's `ai_detection` row lists the matched signals.
- The signals are **not** sent to Jev (`PRIVATE_FACTS`), so Jev's answers are unchanged.

## Evidence (offline, `uv run python evals/jev/ai_css_signals.py`)
152 eval reviews with CSS (dev + holdout, Aug 31 – Sep 25). A human reject that cites AI counts as an "AI reject":

| signals | AI rejects | other rejects | approved |
|---|---|---|---|
| ≥ 3 | 20/75 | 5/39 | 5/38 |
| ≥ 4 | 8/75 | 3/39 | 2/38 |
| ≥ 5 | 2/75 | 1/39 | 0/38 |
| **≥ 6** | **0/75** | **0/39** | **0/38** |

- ISO_VERSE scores **9** in the excerpt Jev saw (10 on the full file). The highest approved project in the eval scored 4.
- `report_v2.py` on dev/holdout is unchanged with the rule active (it never fires there). So the
  rule has **no measured false positives, and also no measured catches** beyond ISO_VERSE. The style looks newer than
  the eval window.
- Taken alone, the signals separate humans' AI rejects from approvals only weakly (e.g. `stock_fonts` hits 66% of approved
  projects). Only the *combination* is distinctive.

## Known weaknesses / ideas for later
1. **Validate on fresh data** (Oct onward), once there are human labels: count fires, and bounced
   approvals, at 5/6/7 signals. Retune `REJECT_AT`.
2. **Teach Jev the modern style** (the better long-term fix): add these habits to the `ai_code` "true" criteria
   and/or pass the signal list as a computed fact, then re-run the dev and holdout Jev evals (about $0.10) before shipping.
   This changes every `ai_code` score, which is why it wasn't done right away.
3. Use the **full stylesheet**, not just the excerpt (the evidence step already downloads it). This needs eval
   evidence regenerated with full text.
4. The same style shows up in HTML (`class="eyebrow"`, `reveal`) and JS (`IntersectionObserver` adding
   `is-visible`). Cross-file signals could catch Tailwind or inline-style projects that have no CSS file.
5. Weight the signals: rare/specific ones (noise texture, `letter-spacing: 0`, `.reveal`) are stronger than
   common ones (`clamp`, stock fonts).
6. Other options considered: lowering the Jev `ai_code` threshold to 0.65 gives +9 rejects on dev+holdout,
   7 of which humans also rejected and 2 approved. That was rejected as too blunt.
