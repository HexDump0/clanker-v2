"""Strictly resolve director-selected visible text against a captured DOM snapshot."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from clanker.review.video.models import (
    Box,
    EvidenceCapture,
    HighlightResolution,
    VisibleElement,
)

_WHITESPACE = re.compile(r"\s+")
_TYPOGRAPHIC = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


@dataclass(frozen=True, slots=True)
class TargetResult:
    box: Box | None
    resolution: HighlightResolution
    detail: str


def normalize_visible_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).translate(_TYPOGRAPHIC)
    return _WHITESPACE.sub(" ", value).strip().casefold()


def _contains(outer: Box, inner: Box, *, tolerance: float = 1.0) -> bool:
    return (
        outer.x <= inner.x + tolerance
        and outer.y <= inner.y + tolerance
        and outer.x + outer.width >= inner.x + inner.width - tolerance
        and outer.y + outer.height >= inner.y + inner.height - tolerance
    )


def _mostly_inside(outer: Box, inner: Box, share: float = 0.9) -> bool:
    """Inner overlaps outer by at least ``share`` of its area. Text-extent boxes (a heading's
    glyphs) can poke a pixel or two outside their wrapper, so strict containment fails."""
    w = min(outer.x + outer.width, inner.x + inner.width) - max(outer.x, inner.x)
    h = min(outer.y + outer.height, inner.y + inner.height) - max(outer.y, inner.y)
    return w > 0 and h > 0 and w * h >= share * inner.area


def _leaf_matches(matches: list[VisibleElement]) -> list[VisibleElement]:
    """Drop ancestor elements while preserving repeated independent matches."""
    leaves: list[VisibleElement] = []
    for candidate in sorted(matches, key=lambda item: item.box.area):
        if any(
            _contains(candidate.box, leaf.box) or _mostly_inside(candidate.box, leaf.box)
            for leaf in leaves
        ):
            continue
        if not any(
            abs(candidate.box.x - leaf.box.x) < 1
            and abs(candidate.box.y - leaf.box.y) < 1
            and abs(candidate.box.width - leaf.box.width) < 1
            and abs(candidate.box.height - leaf.box.height) < 1
            for leaf in leaves
        ):
            leaves.append(candidate)
    return leaves


def resolve_highlight(capture: EvidenceCapture, requested_text: str | None) -> TargetResult:
    if not requested_text:
        return TargetResult(None, HighlightResolution.NOT_REQUESTED, "director requested no text")
    needle = normalize_visible_text(requested_text)
    if len(needle) < 4:
        return TargetResult(None, HighlightResolution.UNSAFE, "highlight text is too short")

    normalized = [(element, normalize_visible_text(element.text)) for element in capture.elements]
    matches = [element for element, text in normalized if text == needle]
    match_kind = "exact"
    if not matches:
        matches = [element for element, text in normalized if needle in text]
        match_kind = "contained"
    if not matches:
        return TargetResult(None, HighlightResolution.MISSING, "text was not in captured DOM")

    leaves = _leaf_matches(matches)
    if len(leaves) != 1:
        return TargetResult(
            None,
            HighlightResolution.AMBIGUOUS,
            f"{len(leaves)} independent {match_kind} matches",
        )
    box = leaves[0].box
    viewport_area = capture.viewport_width * capture.viewport_height
    if box.area > viewport_area * 0.55 or (
        box.width > capture.viewport_width * 0.96
        and box.height > capture.viewport_height * 0.45
    ):
        return TargetResult(None, HighlightResolution.UNSAFE, "matched element is too large")
    return TargetResult(box, HighlightResolution.RESOLVED, f"unique {match_kind} match")
