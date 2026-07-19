"""One-shot multimodal video director.

The model sees clean screenshots and trusted review findings. It performs editorial
selection only: scene order, concise copy, and optional exact visible highlight text.
It never browses and cannot return URLs, selectors, coordinates, timing, or styling.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Protocol

from pydantic_ai import Agent, BinaryContent, PromptedOutput
from pydantic_ai.models.openrouter import OpenRouterModelSettings

from clanker.config import Settings
from clanker.llm import build_model
from clanker.review.models import VideoEvidence
from clanker.review.video.models import EvidenceCapture, VideoPlan, VideoProject

DIRECTOR_INSTRUCTIONS = """\
You are the visual editor for a short, evidence-based software review video.

You receive trusted review findings and one clean browser screenshot per finding. Choose
one to three non-redundant scenes that most clearly explain the verdict. Prefer one
primary piece of evidence; use corroborating evidence only when it adds real proof.

For every chosen scene:
- reference only an evidence_id supplied to you;
- write a plain, specific title and one concise factual explanation;
- copy an exact visible text string into highlight_text only when that text is the best
  thing to point at and is distinctive on the screenshot;
- otherwise return highlight_text=null. This is a good outcome for blank, visual, or
  ambiguous pages;
- reference only supplied fix_ids.

Do not alter the verdict, invent findings, browse, infer a URL, or return selectors,
coordinates, timing, camera instructions, visual styling, narration, or markdown.
The application uses a minimal flat design with no gradients or decorative effects.
"""


class DirectorError(RuntimeError):
    pass


class Director(Protocol):
    async def direct(
        self,
        project: VideoProject,
        evidence: Sequence[VideoEvidence],
        captures: Sequence[EvidenceCapture],
    ) -> VideoPlan: ...


def build_director_model_settings(settings: Settings) -> OpenRouterModelSettings:
    model_settings = OpenRouterModelSettings(timeout=settings.agent_timeout)
    if settings.video_director_provider_pins and settings.ai_provider == "openrouter":
        model_settings["openrouter_provider"] = {
            "only": settings.video_director_provider_pins,
            "allow_fallbacks": settings.video_director_allow_fallbacks,
        }
    return model_settings


def create_director_agent(settings: Settings) -> Agent[None, VideoPlan]:
    return Agent(
        build_model(settings, settings.video_director_model_name),
        output_type=PromptedOutput(VideoPlan),
        instructions=DIRECTOR_INSTRUCTIONS,
        model_settings=build_director_model_settings(settings),
        retries=2,
    )


class VisionDirector:
    def __init__(self, settings: Settings, *, agent: Agent[None, VideoPlan] | None = None) -> None:
        self._agent = agent or create_director_agent(settings)
        self.model_calls = 1
        self.last_usage: dict[str, int] | None = None

    async def direct(
        self,
        project: VideoProject,
        evidence: Sequence[VideoEvidence],
        captures: Sequence[EvidenceCapture],
    ) -> VideoPlan:
        capture_by_id = {capture.evidence_id: capture for capture in captures}
        available = [item for item in evidence if item.id in capture_by_id][:5]
        if not available:
            raise DirectorError("no captured evidence is available to direct")

        trusted_context = {
            "project": project.model_dump(mode="json"),
            "evidence": [item.model_dump(mode="json") for item in available],
            "image_order": [item.id for item in available],
        }
        content: list[str | BinaryContent] = [
            "Trusted review context and screenshot order:\n"
            + json.dumps(trusted_context, ensure_ascii=False, indent=2)
        ]
        for index, item in enumerate(available, 1):
            capture = capture_by_id[item.id]
            content.extend(
                [
                    f"Screenshot {index}: evidence_id={item.id}",
                    BinaryContent(
                        data=capture.screenshot_path.read_bytes(), media_type="image/png"
                    ),
                ]
            )

        try:
            result = await self._agent.run(content)
        except Exception as exc:
            raise DirectorError(f"vision director failed: {exc}") from exc
        plan = result.output
        usage = getattr(result, "usage", None)
        if usage is not None:
            self.last_usage = {
                name: int(getattr(usage, name, 0) or 0)
                for name in ("requests", "input_tokens", "output_tokens", "total_tokens")
            }
        allowed_evidence = {item.id: item for item in available}
        max_fix_id = len(project.required_fixes)
        for scene in plan.scenes:
            source = allowed_evidence.get(scene.evidence_id)
            if source is None:
                raise DirectorError(f"director selected unknown evidence: {scene.evidence_id}")
            if any(fix_id not in source.fix_ids or fix_id > max_fix_id for fix_id in scene.fix_ids):
                raise DirectorError(
                    f"director scene {scene.evidence_id} references an unsupported fix"
                )
        return plan
