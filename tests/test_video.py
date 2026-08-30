from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from clanker.config import Settings
from clanker.review.models import VideoEvidence
from clanker.review.runner import ReviewRunner
from clanker.review.video.capture import CapturePolicy, capture_evidence
from clanker.review.video.compositor import RenderedVideo, build_composition
from clanker.review.video.director import (
    DirectorError,
    VisionDirector,
    build_director_model_settings,
)
from clanker.review.video.models import (
    Box,
    ComposedScene,
    DirectedScene,
    EvidenceCapture,
    HighlightResolution,
    SceneRole,
    VideoPlan,
    VideoProject,
    VisibleElement,
)
from clanker.review.video.pipeline import VideoPipelineError, generate_review_video
from clanker.review.video.targeting import normalize_visible_text, resolve_highlight
from tests.test_review import make_review


def make_capture(tmp_path: Path, *, elements: list[VisibleElement]) -> EvidenceCapture:
    screenshot = tmp_path / "e1.png"
    screenshot.write_bytes(b"fake png")
    return EvidenceCapture(
        evidence_id="e1",
        requested_url="https://example.com/repo",
        final_url="https://example.com/repo",
        http_status=404,
        page_title="Not found",
        captured_at=datetime.now(UTC),
        screenshot_path=screenshot,
        viewport_width=1280,
        viewport_height=720,
        elements=elements,
    )


def make_project() -> VideoProject:
    return VideoProject(
        project_name="ferrocompiler",
        project_author="idident",
        verdict="REJECT",
        required_fixes=["Provide a public repository URL."],
    )


def test_director_uses_its_own_openrouter_provider_pin():
    settings = Settings(
        _env_file=None,
        ai_provider="openrouter",
        openrouter_provider_only="alibaba",
        video_director_provider_only="nex-agi, another-provider",
        video_director_allow_fallbacks=True,
    )

    model_settings = build_director_model_settings(settings)

    assert model_settings["openrouter_provider"] == {
        "only": ["nex-agi", "another-provider"],
        "allow_fallbacks": True,
    }


def test_director_does_not_inherit_review_provider_pin_and_routes_dynamically():
    settings = Settings(
        _env_file=None,
        ai_provider="openrouter",
        openrouter_provider_only="alibaba",
    )

    assert build_director_model_settings(settings)["openrouter_provider"] == {
        "sort": "throughput",
        "preferred_max_latency": 2.0,
        "max_price": {"prompt": 0.5, "completion": 1.0},
        "require_parameters": True,
        "allow_fallbacks": True,
    }


def make_plan(highlight_text: str | None = "This is not the web page you are looking for"):
    return VideoPlan(
        headline="The repository cannot be reviewed.",
        summary="The submitted GitHub URL opens a not-found page.",
        scenes=[
            DirectedScene(
                evidence_id="e1",
                role=SceneRole.PRIMARY,
                title="Repository not found",
                explanation="The submitted repository URL does not open a public repository.",
                highlight_text=highlight_text,
                fix_ids=[1],
            )
        ],
    )


def test_review_video_evidence_rejects_locator_fields_and_bad_fix_reference():
    with pytest.raises(ValidationError):
        VideoEvidence(
            id="repo",
            check="repo_link_valid",
            url="https://github.com/example/missing",
            finding="Repository is unavailable.",
            selector="main",  # type: ignore[call-arg]
        )


def test_text_normalization_and_nested_element_resolution(tmp_path):
    phrase = "This is not the web page you are looking for"
    capture = make_capture(
        tmp_path,
        elements=[
            VisibleElement(text=phrase, tag="main", box=Box(x=100, y=100, width=600, height=300)),
            VisibleElement(text=phrase, tag="h1", box=Box(x=180, y=160, width=410, height=60)),
        ],
    )
    result = resolve_highlight(capture, "  THIS is not the web page you are looking for  ")
    assert normalize_visible_text("It’s — fine") == "it's - fine"
    assert result.resolution is HighlightResolution.RESOLVED
    assert result.box == Box(x=180, y=160, width=410, height=60)


def test_repeated_or_missing_text_falls_back_without_highlight(tmp_path):
    capture = make_capture(
        tmp_path,
        elements=[
            VisibleElement(text="Not found", tag="p", box=Box(x=10, y=10, width=100, height=20)),
            VisibleElement(text="Not found", tag="p", box=Box(x=500, y=10, width=100, height=20)),
        ],
    )
    repeated = resolve_highlight(capture, "Not found")
    missing = resolve_highlight(capture, "No releases published")
    assert repeated.resolution is HighlightResolution.AMBIGUOUS and repeated.box is None
    assert missing.resolution is HighlightResolution.MISSING and missing.box is None


class FakeAgent:
    def __init__(self, plan: VideoPlan) -> None:
        self.plan = plan
        self.content = None

    async def run(self, content):
        self.content = content
        return SimpleNamespace(output=self.plan)


async def test_vision_director_sends_screenshots_and_rejects_unknown_evidence(tmp_path):
    capture = make_capture(tmp_path, elements=[])
    evidence = [
        VideoEvidence(
            id="e1",
            check="repo_link_valid",
            url="https://example.com/repo",
            finding="The repository URL opens a not-found page.",
            fix_ids=[1],
        )
    ]
    fake = FakeAgent(make_plan())
    director = VisionDirector(Settings(), agent=fake)  # type: ignore[arg-type]
    result = await director.direct(make_project(), evidence, [capture])
    assert result.scenes[0].highlight_text
    assert len(fake.content) == 3

    fake.plan.scenes[0].evidence_id = "invented"
    with pytest.raises(DirectorError, match="unknown evidence"):
        await director.direct(make_project(), evidence, [capture])


def test_minimal_composition_has_bottom_right_fallback_and_no_gradients(tmp_path):
    capture = make_capture(tmp_path, elements=[])
    directed = make_plan(highlight_text=None).scenes[0]
    scene = ComposedScene(
        directed=directed,
        capture=capture,
        resolution=HighlightResolution.NOT_REQUESTED,
        resolution_detail="director requested no text",
    )
    document, duration = build_composition(make_project(), make_plan(None), [scene])
    assert "right:40px;bottom:40px" in document
    assert "data-rect='null'" in document
    assert "gradient" not in document.lower()
    assert duration == 13.0


async def test_capture_keeps_page_metadata_without_freshness_validation(monkeypatch, tmp_path):
    screenshot_log = Mock()
    monkeypatch.setattr("clanker.review.video.capture.logfire.info", screenshot_log)
    async def handle(reader, writer):
        await reader.read(4096)
        body = b"<html><body><h1>Current page content</h1></body></html>"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    evidence = VideoEvidence(
        id="e1",
        check="repo_link_valid",
        url=f"http://127.0.0.1:{port}/evidence",
        finding="The original review finding is trusted.",
    )
    try:
        capture = await capture_evidence(
            evidence,
            tmp_path,
            policy=CapturePolicy(load_timeout=10, settle_seconds=0, allow_private_hosts=True),
        )
    finally:
        server.close()
        await server.wait_closed()
    assert capture.http_status == 200
    assert capture.screenshot_path.is_file()
    assert any(item.text == "Current page content" for item in capture.elements)
    assert screenshot_log.call_args.kwargs["evidence_id"] == "e1"
    assert screenshot_log.call_args.kwargs["screenshot_bytes"] > 0


async def test_capture_plain_text_exposes_line_geometry(monkeypatch, tmp_path):
    monkeypatch.setattr("clanker.review.video.capture.logfire.info", Mock())
    phrase = "This is a Next.js project bootstrapped with create-next-app."
    body = (phrase + "\n" + ("More framework documentation.\n" * 80)).encode()

    async def handle(reader, writer):
        await reader.read(4096)
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    evidence = VideoEvidence(
        id="raw-readme",
        check="readme_boilerplate",
        url=f"http://127.0.0.1:{port}/README.md",
        finding="The README is framework boilerplate.",
    )
    try:
        capture = await capture_evidence(
            evidence,
            tmp_path,
            policy=CapturePolicy(load_timeout=10, settle_seconds=0, allow_private_hosts=True),
        )
    finally:
        server.close()
        await server.wait_closed()

    match = resolve_highlight(capture, phrase)
    assert match.resolution is HighlightResolution.RESOLVED
    assert match.box is not None and match.box.height < 30


async def test_pipeline_records_missing_text_fallback(monkeypatch, tmp_path):
    capture = make_capture(
        tmp_path,
        elements=[VisibleElement(text="Something else", box=Box(x=30, y=30, width=200, height=30))],
    )

    async def fake_capture(*args, **kwargs):
        return capture

    async def fake_render(document, duration, output_path, music_path=None):
        output_path.write_bytes(b"mp4")
        return RenderedVideo(output_path, duration, 3)

    class StaticDirector:
        async def direct(self, project, evidence, captures):
            return make_plan("Text the model imagined")

    monkeypatch.setattr("clanker.review.video.pipeline.capture_evidence", fake_capture)
    monkeypatch.setattr("clanker.review.video.pipeline.render_composition", fake_render)
    evidence = [
        VideoEvidence(
            id="e1",
            check="repo_link_valid",
            url="https://example.com/repo",
            finding="Repository unavailable.",
            fix_ids=[1],
        )
    ]
    result = await generate_review_video(
        project=make_project(),
        evidence=evidence,
        director=StaticDirector(),
        work_dir=tmp_path / "run",
        output_path=tmp_path / "result.mp4",
    )
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["scenes"][0]["resolution"] == "missing"
    assert manifest["scenes"][0]["target_box"] is None


async def test_pipeline_capture_watchdog_prevents_hanging_review(monkeypatch, tmp_path):
    async def hanging_capture(*args, **kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr("clanker.review.video.pipeline.capture_evidence", hanging_capture)
    evidence = [
        VideoEvidence(
            id="e1",
            check="repo_link_valid",
            url="https://example.com/repo",
            finding="Repository unavailable.",
        )
    ]
    with pytest.raises(VideoPipelineError, match="operation timeout"):
        await generate_review_video(
            project=make_project(),
            evidence=evidence,
            director=SimpleNamespace(),  # type: ignore[arg-type]
            work_dir=tmp_path / "run",
            output_path=tmp_path / "result.mp4",
            capture_policy=CapturePolicy(operation_timeout=0.01),
        )


async def test_review_runner_generates_video_from_review_evidence(monkeypatch, tmp_path):
    evidence = VideoEvidence(
        id="readme",
        check="readme_boilerplate",
        url="https://raw.githubusercontent.com/example/repo/main/README.md",
        finding="The README is unchanged framework boilerplate.",
        fix_ids=[1],
    )
    review = make_review(
        verdict="REJECT",
        required_fixes=["Write a project-specific README."],
        video_evidence=[evidence],
    )
    packet = SimpleNamespace(
        to_prompt=lambda: "Review Example",
        cert=SimpleNamespace(
            project_name="Example",
            submitter_username="@builder",
            submitter_name=None,
            description="A project",
            repo_url="https://github.com/example/repo",
            demo_url="https://example.com",
        )
    )

    class ReviewAgent:
        async def run(self, prompt):
            return SimpleNamespace(
                output=review,
                usage=SimpleNamespace(input_tokens=10, output_tokens=5, requests=1),
            )

    async def fake_packet(client, cert_id, tools=None):
        return packet

    async def fake_pdf(*args, **kwargs):
        path = kwargs["output_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"pdf")
        return path

    async def fake_video(**kwargs):
        path = kwargs["output_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mp4")
        return SimpleNamespace(video=SimpleNamespace(path=path))

    monkeypatch.setattr("clanker.review.runner.build_packet", fake_packet)
    monkeypatch.setattr("clanker.review.runner.generate_review_pdf", fake_pdf)
    monkeypatch.setattr("clanker.review.runner.generate_review_video", fake_video)
    settings = Settings(
        _env_file=None,
        video_enabled=True,
        pdf_dir=tmp_path / "pdfs",
        video_dir=tmp_path / "videos",
        video_work_dir=tmp_path / "runs",
    )
    runner = ReviewRunner(
        agent=ReviewAgent(),  # type: ignore[arg-type]
        client=object(),  # type: ignore[arg-type]
        settings=settings,
        video_director=object(),  # type: ignore[arg-type]
    )

    outcome = await runner.review_cert("c1")

    assert outcome.pdf_path == tmp_path / "pdfs/c1.pdf"
    assert outcome.video_path == tmp_path / "videos/c1.mp4"
    assert outcome.video_error is None
