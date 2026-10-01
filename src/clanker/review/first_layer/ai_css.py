"""Code rule for the newer (GPT-5/Codex-era) AI CSS house style.

Jev's ``ai_code`` criteria describe older AI tells (gradient heroes, glassmorphism,
``/* ===== */`` banners, emoji comments). Newer generated CSS has none of those and no
comments at all, but shares a very consistent set of habits. Counting them in the CSS
excerpts is deterministic and cheap. In the eval set (152 CSS-bearing reviews, Aug 31 –
Sep 25) no human-approved project scored above 4, while the ISO_VERSE ship that prompted
this (Oct 1) scored 9. Background, data and ideas for improving this are in
``AI/notes/modern-ai-css-rule-2026-10-01.md``.
"""

from __future__ import annotations

import re

SIGNALS: dict[str, re.Pattern[str]] = {
    "noise_texture": re.compile(r"fractalNoise|feTurbulence", re.I),
    "eyebrow_label": re.compile(r"\.eyebrow\b|\.kicker\b|\.overline\b", re.I),
    "reveal_animation": re.compile(r"\.reveal\b|is-visible|\.in-view\b", re.I),
    "letter_spacing_0": re.compile(r"letter-spacing:\s*0\s*[;}]", re.I),
    "width_min": re.compile(r"width:\s*min\(", re.I),
    "logical_props": re.compile(
        r"margin-inline|padding-block|padding-inline|margin-block|inset:\s*0\s*;", re.I
    ),
    "clamp": re.compile(r"clamp\(", re.I),
    "stock_fonts": re.compile(
        r"DM Sans|DM Mono|Manrope|Space Grotesk|Instrument Serif|Fraunces|JetBrains Mono|"
        r"Inter\b",
        re.I,
    ),
    "color_scheme": re.compile(r"color-scheme", re.I),
}
# Four or more design-token variables with stock names (--paper, --ink, --muted, --line, ...).
NAMED_VARS = re.compile(
    r"--(paper|ink|muted|line|surface|accent|bg|fg|text|panel|card|border|primary|secondary|"
    r"shadow|radius)[\w-]*\s*:",
    re.I,
)
NAMED_VARS_MIN = 4
# Out of 10 signals. 6 had zero approved hits in the eval; keep it conservative.
REJECT_AT = 6


def modern_ai_css_signals(css: str) -> list[str]:
    """Names of the modern AI CSS habits present in ``css`` (excerpts are fine)."""
    found = [name for name, pattern in SIGNALS.items() if pattern.search(css)]
    if len(NAMED_VARS.findall(css)) >= NAMED_VARS_MIN:
        found.append("named_token_palette")
    return found
