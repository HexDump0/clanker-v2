"""End-to-end screenshot-first video generation service."""

from __future__ import annotations

import asyncio
import json
import logging
import time
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
    VideoProject,
    VideoRunManifest,
)
from clanker.review.video.targeting import resolve_highlight

logger = logging.getLogger(__name__)


class VideoPipelineError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VideoGenerationResult:
    video: RenderedVideo
    manifest_path: Path
    capture_failures: dict[str, str]


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
    capture_dir = run_dir / "captures"
    run_dir.mkdir(parents=True, exist_ok=True)

    captures = []
    failures: dict[str, str] = {}
    audit: list[dict[str, object]] = []
    for item in evidence[:5]:
        started = time.perf_counter()
        try:
            capture = await asyncio.wait_for(
                capture_evidence(item, capture_dir, policy=capture_policy),
                timeout=capture_policy.operation_timeout,
            )
        except TimeoutError:
            exc = CaptureError(
                f"capture exceeded the {capture_policy.operation_timeout:g}s operation timeout"
            )
            failures[item.id] = str(exc)
            audit.append(
                {
                    "stage": "capture",
                    "evidence_id": item.id,
                    "ok": False,
                    "seconds": round(time.perf_counter() - started, 3),
                    "error": str(exc),
                }
            )
            logger.warning("Video evidence capture %s timed out: %s", item.id, exc)
        except CaptureError as exc:
            failures[item.id] = str(exc)
            audit.append(
                {
                    "stage": "capture",
                    "evidence_id": item.id,
                    "ok": False,
                    "seconds": round(time.perf_counter() - started, 3),
                    "error": str(exc),
                }
            )
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
