"""End-to-end screenshot-first video generation service.

Two entry points share capture, highlight resolution, composition, and encoding:

- ``generate_reject_video``: first-layer rejections. Code plans the scenes from the reject
  reasons (``TemplateDirector``); no model is called. Reasons with no public page, and live
  pages that fail to capture, become locally rendered text cards.
- ``generate_review_video``: the older path where a vision model directs scenes from
  review evidence (``VisionDirector``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from clanker.review.models import VideoEvidence
from clanker.review.video.capture import (
    DEFAULT_CAPTURE_POLICY,
    CaptureError,
    CapturePolicy,
    capture_evidence,
)
from clanker.review.video.compositor import RenderedVideo, build_composition, render_composition
from clanker.review.video.director import Director
from clanker.review.video.models import (
    ComposedScene,
    EvidenceCapture,
    VideoPlan,
    VideoProject,
    VideoRunManifest,
)
from clanker.review.video.targeting import resolve_highlight
from clanker.review.video.template_director import (
    RejectVideoInputs,
    TemplateDirector,
    evidence_for,
    plan_scenes,
    render_text_card,
)

logger = logging.getLogger(__name__)


class VideoPipelineError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VideoGenerationResult:
    video: RenderedVideo
    manifest_path: Path
    capture_failures: dict[str, str]


async def _capture_all(
    evidence: Sequence[VideoEvidence], capture_dir: Path, policy: CapturePolicy
) -> tuple[list[EvidenceCapture], dict[str, str], list[dict[str, object]]]:
    """Capture each evidence page under a watchdog; failures are recorded, not raised."""
    captures: list[EvidenceCapture] = []
    failures: dict[str, str] = {}
    audit: list[dict[str, object]] = []
    for item in evidence[:5]:
        started = time.perf_counter()
        try:
            capture = await asyncio.wait_for(
                capture_evidence(item, capture_dir, policy=policy),
                timeout=policy.operation_timeout,
            )
        except TimeoutError:
            exc = CaptureError(
                f"capture exceeded the {policy.operation_timeout:g}s operation timeout"
            )
            failures[item.id] = str(exc)
            audit.append(_capture_failure(item.id, started, exc))
            logger.warning("Video evidence capture %s timed out: %s", item.id, exc)
        except CaptureError as exc:
            failures[item.id] = str(exc)
            audit.append(_capture_failure(item.id, started, exc))
            logger.warning("Video evidence capture %s failed: %s", item.id, exc)
        else:
            captures.append(capture)
            audit.append(
                {
                    "stage": "capture",
                    "evidence_id": item.id,
                    "ok": True,
                    "seconds": round(time.perf_counter() - started, 3),
                    "http_status": capture.http_status,
                    "visible_elements": len(capture.elements),
                }
            )
            logger.info(
                "Captured video evidence %s: %s (%s)",
                item.id,
                capture.final_url,
                capture.http_status,
            )
    return captures, failures, audit


def _capture_failure(evidence_id: str, started: float, exc: Exception) -> dict[str, object]:
    return {
        "stage": "capture",
        "evidence_id": evidence_id,
        "ok": False,
        "seconds": round(time.perf_counter() - started, 3),
        "error": str(exc),
    }


async def _compose_and_render(
    *,
    project: VideoProject,
    plan: VideoPlan,
    captures: Sequence[EvidenceCapture],
    run_dir: Path,
    output_path: Path,
    music_path: Path | None,
    failures: dict[str, str],
    audit: list[dict[str, object]],
) -> VideoGenerationResult:
    """Resolve highlights, compose, encode, and write the run manifest."""
    capture_by_id = {capture.evidence_id: capture for capture in captures}
    scenes: list[ComposedScene] = []
    for directed in plan.scenes:
        capture = capture_by_id.get(directed.evidence_id)
        if capture is None:
            raise VideoPipelineError(
                f"director selected evidence without a screenshot: {directed.evidence_id}"
            )
        target = resolve_highlight(capture, directed.highlight_text)
        logger.info(
            "Resolved video target %s: %s (%s)",
            directed.evidence_id,
            target.resolution.value,
            target.detail,
        )
        scenes.append(
            ComposedScene(
                directed=directed,
                capture=capture,
                target_box=target.box,
                resolution=target.resolution,
                resolution_detail=target.detail,
            )
        )
        audit.append(
            {
                "stage": "target_resolution",
                "evidence_id": directed.evidence_id,
                "resolution": target.resolution.value,
                "detail": target.detail,
            }
        )

    document, duration = build_composition(project, plan, scenes)
    started = time.perf_counter()
    video = await render_composition(document, duration, output_path, music_path=music_path)
    audit.append(
        {
            "stage": "render_and_encode",
            "ok": True,
            "seconds": round(time.perf_counter() - started, 3),
            "duration_seconds": video.duration_seconds,
            "size_bytes": video.size_bytes,
        }
    )
    manifest = VideoRunManifest(
        project=project,
        plan=plan,
        scenes=scenes,
        output_path=video.path,
    )
    manifest_path = run_dir / "manifest.json"
    payload = json.loads(manifest.model_dump_json())
    payload["capture_failures"] = failures
    payload["render"] = {
        "duration_seconds": video.duration_seconds,
        "size_bytes": video.size_bytes,
    }
    payload["audit"] = audit
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return VideoGenerationResult(video, manifest_path, failures)


async def generate_review_video(
    *,
    project: VideoProject,
    evidence: list[VideoEvidence],
    director: Director,
    work_dir: Path,
    output_path: Path,
    capture_policy: CapturePolicy = DEFAULT_CAPTURE_POLICY,
    music_path: Path | None = None,
) -> VideoGenerationResult:
    """Capture, direct once, resolve strictly, and render.

    Capture-time HTTP status and page contents are stored as metadata only.
    """
    if not evidence:
        raise VideoPipelineError("review supplied no browser-visible video evidence")
    run_dir = work_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    captures, failures, audit = await _capture_all(
        evidence, run_dir / "captures", capture_policy
    )
    if not captures:
        raise VideoPipelineError(f"all evidence captures failed: {failures}")

    started = time.perf_counter()
    plan = await director.direct(project, evidence, captures)
    audit.append(
        {
            "stage": "vision_director",
            "ok": True,
            "seconds": round(time.perf_counter() - started, 3),
            "model_calls": getattr(director, "model_calls", 1),
            "screenshots": len(captures),
            "scenes": len(plan.scenes),
            "usage": getattr(director, "last_usage", None),
        }
    )
    return await _compose_and_render(
        project=project,
        plan=plan,
        captures=captures,
        run_dir=run_dir,
        output_path=output_path,
        music_path=music_path,
        failures=failures,
        audit=audit,
    )


async def generate_reject_video(
    *,
    reasons: Sequence[str],
    inputs: RejectVideoInputs,
    seed: str,
    work_dir: Path,
    output_path: Path,
    capture_policy: CapturePolicy = DEFAULT_CAPTURE_POLICY,
    music_path: Path | None = None,
) -> VideoGenerationResult:
    """First-layer rejection video with no model calls.

    ``seed`` (use the cert id) keeps wording stable per submission. At most three scenes, in
    the same priority order as the reject message.
    """
    specs = plan_scenes(reasons, inputs, seed)
    if not specs:
        raise VideoPipelineError(f"no reject reason maps to a video scene: {list(reasons)}")
    run_dir = work_dir
    capture_dir = run_dir / "captures"
    run_dir.mkdir(parents=True, exist_ok=True)

    live = evidence_for(specs)
    captures, failures, audit = await _capture_all(live, capture_dir, capture_policy)
    captured = {capture.evidence_id for capture in captures}
    for spec in specs:
        if spec.id in captured:
            continue
        if spec.url:
            # The page couldn't be captured (bot wall, timeout, private host): show where the
            # problem is as a text card instead of dropping the scene.
            spec.card_lines = [spec.url]
            stage = "text_card_fallback"
        else:
            stage = "text_card"
        started = time.perf_counter()
        try:
            captures.append(await render_text_card(spec, capture_dir))
        except Exception as exc:  # a failed card only costs that scene
            failures[spec.id] = f"text card failed: {exc}"
            audit.append({"stage": stage, "evidence_id": spec.id, "ok": False, "error": str(exc)})
            logger.warning("Text card %s failed: %s", spec.id, exc)
            continue
        audit.append(
            {
                "stage": stage,
                "evidence_id": spec.id,
                "ok": True,
                "seconds": round(time.perf_counter() - started, 3),
            }
        )
    if not captures:
        raise VideoPipelineError(f"no scene could be captured or rendered: {failures}")

    project = VideoProject(
        project_name=inputs.project_name,
        project_author=inputs.ctx.submitter or "",
        verdict="REJECTED",
        required_fixes=[spec.fix for spec in specs],
    )
    plan = await TemplateDirector(specs, seed).direct(project, live, captures)
    audit.append(
        {"stage": "template_director", "ok": True, "model_calls": 0, "scenes": len(plan.scenes)}
    )
    return await _compose_and_render(
        project=project,
        plan=plan,
        captures=captures,
        run_dir=run_dir,
        output_path=output_path,
        music_path=music_path,
        failures=failures,
        audit=audit,
    )
