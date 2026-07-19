"""The contract between the video director (pass 1) and the recorder (pass 2).

A ``VideoScript`` is the director's validated output: an ordered list of fully
resolved scenes. The recorder replays it deterministically — it never decides
where to go or what to say, so a bad page at replay time skips one scene
instead of invalidating the video.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SceneTarget(BaseModel):
    """What to spotlight on the page. Exactly one of the three forms.

    - ``text``: first element whose visible text contains this snippet
      (robust on pages we don't control — anchor on what the director saw);
    - ``selector``: CSS selector, for well-known stable structures;
    - ``viewport``: frame the whole visible page (broken/blank pages, 404s).
    """

    text: str | None = None
    selector: str | None = None
    viewport: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> SceneTarget:
        if sum((self.text is not None, self.selector is not None, self.viewport)) != 1:
            raise ValueError("target must set exactly one of text, selector, viewport")
        return self


class Scene(BaseModel):
    """One finding, demonstrated in place: open ``url``, spotlight ``target``,
    show a callout explaining the problem and the fix."""

    url: str
    target: SceneTarget
    title: str = Field(description="Short problem statement shown as the callout heading.")
    body: str = Field(description="What is wrong and how to fix it, 1-3 sentences.")
    hold_seconds: float = Field(default=5.0, ge=1.0, le=15.0)


class VideoScript(BaseModel):
    """Everything the recorder needs to produce one review video."""

    project_name: str
    verdict: str
    summary: str = Field(default="", description="One-line intro shown on the title card.")
    scenes: list[Scene] = Field(min_length=1)
    required_fixes: list[str] = Field(default_factory=list)
