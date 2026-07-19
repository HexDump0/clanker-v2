"""Validated contracts for screenshot-first review videos.

The review agent supplies semantic evidence. A separate vision model selects scenes
and optionally names exact visible text. Application code alone resolves rectangles
and renders the video. Keeping those boundaries explicit makes weak director output
safe: an unusable highlight becomes an ordinary bottom-right callout scene.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Box(BaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)

    @property
    def area(self) -> float:
        return self.width * self.height


class VisibleElement(BaseModel):
    """Visible DOM text and bounds captured in the same state as the screenshot."""

    text: str
    box: Box
    tag: str = ""


class EvidenceCapture(BaseModel):
    evidence_id: str
    requested_url: str
    final_url: str
    http_status: int | None = None
    page_title: str = ""
    captured_at: datetime
    screenshot_path: Path
    viewport_width: int = Field(gt=0)
    viewport_height: int = Field(gt=0)
    elements: list[VisibleElement] = Field(default_factory=list)


class SceneRole(StrEnum):
    PRIMARY = "primary"
    CORROBORATING = "corroborating"


class DirectedScene(BaseModel):
    """One editorial decision from the vision director.

    There are deliberately no URLs, selectors, rectangles, timing, or styling fields.
    """

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    role: SceneRole
    title: str = Field(min_length=1, max_length=80)
    explanation: str = Field(min_length=1, max_length=260)
    highlight_text: str | None = Field(
        default=None,
        max_length=240,
        description=(
            "Exact text visibly present in the screenshot, or null when no useful target exists."
        ),
    )
    fix_ids: list[int] = Field(default_factory=list, max_length=4)

    @field_validator("highlight_text")
    @classmethod
    def _blank_highlight_is_none(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None


class VideoPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=1, max_length=100)
    summary: str = Field(
        min_length=1,
        max_length=240,
        description=(
            "One sentence addressed to the project's author in the second person, "
            "opening with the outcome, e.g. 'Your project was rejected because …' "
            "(or 'approved'/'needs a human reviewer' to match the verdict)."
        ),
    )
    scenes: list[DirectedScene] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def _unique_evidence(self) -> VideoPlan:
        ids = [scene.evidence_id for scene in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("each evidence item may appear in at most one scene")
        return self


class HighlightResolution(StrEnum):
    RESOLVED = "resolved"
    NOT_REQUESTED = "not_requested"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    UNSAFE = "unsafe"


class ComposedScene(BaseModel):
    directed: DirectedScene
    capture: EvidenceCapture
    target_box: Box | None = None
    resolution: HighlightResolution
    resolution_detail: str = ""


class VideoProject(BaseModel):
    project_name: str
    project_author: str = ""
    verdict: str
    required_fixes: list[str] = Field(default_factory=list)


class VideoRunManifest(BaseModel):
    project: VideoProject
    plan: VideoPlan
    scenes: list[ComposedScene]
    output_path: Path


# Legacy live-page recorder contract. Kept for callers of record_video_script while
# the screenshot-first pipeline replaces it in orchestration.
class SceneTarget(BaseModel):
    text: str | None = None
    selector: str | None = None
    viewport: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> SceneTarget:
        if sum((self.text is not None, self.selector is not None, self.viewport)) != 1:
            raise ValueError("target must set exactly one of text, selector, viewport")
        return self


class Scene(BaseModel):
    url: str
    target: SceneTarget
    title: str
    body: str
    hold_seconds: float = Field(default=5.0, ge=1.0, le=15.0)


class VideoScript(BaseModel):
    project_name: str
    verdict: str
    summary: str = ""
    scenes: list[Scene] = Field(min_length=1)
    required_fixes: list[str] = Field(default_factory=list)
