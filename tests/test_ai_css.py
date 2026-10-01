"""The modern AI CSS code rule (see AI/notes/modern-ai-css-rule-2026-10-01.md)."""

from __future__ import annotations

from clanker.review.first_layer import to_review_output
from clanker.review.first_layer.ai_css import REJECT_AT, modern_ai_css_signals
from clanker.review.models import CheckStatus
from tests.test_first_layer import jev_answers, make_reviewer, packet_for

# Trimmed from the ISO_VERSE ship (Oct 2026) that humans judged AI-styled.
MODERN_AI_CSS = """
:root {
    color-scheme: light;
    --paper: #f5f1e8; --ink: #172a26; --muted: #68736b; --line: rgba(23, 42, 38, .16);
    --sans: "DM Sans", sans-serif; --display: "Manrope", sans-serif;
}
body::before { inset: 0; background-image: url("data:image/svg+xml,%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise'/%3E"); }
.shell { width: min(var(--page-width), calc(100% - 64px)); margin-inline: auto; }
.eyebrow { font-family: var(--mono); letter-spacing: 0; text-transform: uppercase; }
.reveal { opacity: 0; } .reveal.is-visible { opacity: 1; }
"""  # noqa: E501

HAND_WRITTEN_CSS = """
body { background-color: #222; color: white; font-family: Arial; }
#game { margin: 20px auto; width: 400px; }
.btn { padding: 10px; border-radius: 5px; }
"""


def css_file(css: str) -> list[dict]:
    return [{"path": "style.css", "total_chars": len(css), "excerpt": css}]


def test_signals_on_modern_and_hand_written_css():
    assert len(modern_ai_css_signals(MODERN_AI_CSS)) >= REJECT_AT
    assert modern_ai_css_signals(HAND_WRITTEN_CSS) == []


async def test_modern_ai_css_rejects_even_when_jev_is_under_threshold(client, dashboard):
    packet = await packet_for(client, dashboard)
    reviewer = make_reviewer(jev_answers(ai_code=0.67), files=css_file(MODERN_AI_CSS))
    result = await reviewer.review(packet)

    assert result.verdict == "REJECT"
    assert result.reasons == ["ai_code"]  # once, not again from Jev
    detail = to_review_output(result).checks.ai_detection
    assert detail.status == CheckStatus.FAIL and "Modern AI CSS style" in detail.details


async def test_modern_ai_css_not_sent_to_jev(client, dashboard):
    calls: list = []
    packet = await packet_for(client, dashboard)
    await make_reviewer(jev_answers(), calls, files=css_file(MODERN_AI_CSS)).review(packet)
    state, _ = calls[0]
    assert "modern_ai_css_signals" not in state["computed_facts"]


async def test_few_signals_pass_with_a_near_miss_note(client, dashboard):
    css = ":root { color-scheme: dark; } .a { width: min(10px, 1vw); margin-inline: auto; }"
    css += " .b { font: 1rem 'DM Sans'; }"
    packet = await packet_for(client, dashboard)
    result = await make_reviewer(jev_answers(), files=css_file(css)).review(packet)

    assert result.verdict == "PASS"
    assert any("modern AI CSS signals 4" in note for note in result.near_misses)
