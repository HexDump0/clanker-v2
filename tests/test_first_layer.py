"""First-layer review wiring: FirstLayerReviewer (fake Jev) and the ReviewRunner path."""

from __future__ import annotations

import shutil
from types import SimpleNamespace
from typing import Any

import pytest

from clanker.config import Settings
from clanker.review.first_layer import FirstLayerReviewer, to_review_output
from clanker.review.models import CheckStatus, ReviewVerdict
from clanker.review.packet import build_packet
from clanker.review.runner import ReviewRunner
from tests.conftest import make_cert

RAW_README = "https://raw.githubusercontent.com/x/y/main/README.md"


def jev_answers(**scores: float) -> dict[str, Any]:
    answers: dict[str, Any] = {
        key: {"noul": 0.0}
        for key in (
            "ai_code", "ai_readme", "readme_thin", "demo_not_testable", "demo_broken",
            "feedback_ignored", "ai_undeclared", "not_eligible", "needs_api_key",
        )
    }  # fmt: skip
    for key, value in scores.items():
        answers[key] = {"noul": value}
    answers["project_type"] = {"choice": "web_app", "confidence": 0.9}
    answers["main_reason"] = {"choice": "none", "confidence": 0.9}
    return answers


def make_reviewer(
    answers: dict[str, Any],
    calls: list | None = None,
    files: list | None = None,
    history: dict[str, Any] | None = None,
) -> FirstLayerReviewer:
    async def ask(state, questions):
        if calls is not None:
            calls.append((state, questions))
        return answers, 1234

    reviewer = FirstLayerReviewer(
        Settings(_env_file=None, openrouter_api_key=""), ask=ask, banner_agent=object()
    )

    async def no_evidence(prompt: str, cutoff: str) -> dict[str, Any]:
        return {
            "files": files or [],
            "release_assets": None,
            "banner": "project_screenshot",
            "history": history,
        }

    reviewer._evidence = no_evidence  # type: ignore[method-assign]
    return reviewer


async def packet_for(client, dashboard, **overrides):
    dashboard.details["c1"] = {**make_cert("c1"), "readmeUrl": RAW_README, **overrides}
    return await build_packet(client, "c1")


async def test_first_layer_passes_clean_submission_to_human(client, dashboard):
    calls: list = []
    packet = await packet_for(client, dashboard)
    result = await make_reviewer(jev_answers(ai_code=0.6), calls).review(packet)

    assert result.verdict == "PASS"
    assert result.reasons == []
    assert result.message is None
    assert result.jev_input_tokens == 1234
    assert any("AI-heavy code 0.60" in near for near in result.near_misses)
    state, questions = calls[0]
    assert "ai_code" in questions and "project_type" in questions
    assert "code_excerpts" in state

    review = to_review_output(result)
    assert review.verdict == ReviewVerdict.FLAG_FOR_HUMAN
    assert review.checks.readme_is_raw_github.status == CheckStatus.PASS
    # Unchecked rubric rows are skipped for the human, never passed.
    assert review.checks.commit_authorship.status == CheckStatus.SKIP


async def test_first_layer_rejects_over_threshold_with_message(client, dashboard):
    packet = await packet_for(client, dashboard)
    result = await make_reviewer(jev_answers(ai_readme=0.95)).review(packet)

    assert result.verdict == "REJECT"
    assert result.reasons == ["ai_readme"]
    assert result.message and "README" in result.message
    review = to_review_output(result)
    assert review.verdict == ReviewVerdict.REJECT
    assert review.checks.ai_detection.status == CheckStatus.FAIL
    assert review.required_fixes


async def test_first_layer_rejects_non_raw_readme_by_code(client, dashboard):
    packet = await packet_for(
        client, dashboard, readmeUrl="https://github.com/x/y/blob/main/README.md"
    )
    result = await make_reviewer(jev_answers()).review(packet)
    assert result.verdict == "REJECT"
    assert "readme_not_raw" in result.reasons


def test_first_layer_requires_openrouter_key():
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        FirstLayerReviewer(Settings(_env_file=None, openrouter_api_key=""))


def fake_artifacts(monkeypatch, packet, videos: list) -> None:
    async def fake_packet(client, cert_id, tools=None):
        return packet

    async def fake_pdf(*args, **kwargs):
        path = kwargs["output_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"pdf")
        return path

    async def fake_reject_video(**kwargs):
        videos.append(kwargs)
        path = kwargs["output_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mp4")
        return SimpleNamespace(video=SimpleNamespace(path=path))

    monkeypatch.setattr("clanker.review.runner.build_packet", fake_packet)
    monkeypatch.setattr("clanker.review.runner.generate_first_layer_pdf", fake_pdf)
    monkeypatch.setattr("clanker.review.runner.generate_reject_video", fake_reject_video)


def runner_settings(tmp_path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        pdf_dir=tmp_path / "pdfs",
        video_dir=tmp_path / "videos",
        video_work_dir=tmp_path / "runs",
        **overrides,
    )


async def test_runner_first_layer_reject_posts_message_pdf_and_video(
    monkeypatch, tmp_path, client, dashboard
):
    packet = await packet_for(client, dashboard)
    videos: list = []
    fake_artifacts(monkeypatch, packet, videos)
    runner = ReviewRunner(
        first_layer=make_reviewer(jev_answers(ai_code=0.9)),
        client=object(),  # type: ignore[arg-type]
        settings=runner_settings(tmp_path, video_enabled=True),
    )

    outcome = await runner.review_cert("c1")

    assert outcome.review.verdict == ReviewVerdict.REJECT
    assert outcome.reject_message
    assert outcome.first_layer is not None and outcome.first_layer.reasons == ["ai_code"]
    assert outcome.pdf_path == tmp_path / "pdfs/c1.pdf"
    assert outcome.video_path == tmp_path / "videos/c1.mp4"
    assert outcome.input_tokens == 1234 and outcome.output_tokens == 0
    assert videos[0]["reasons"] == ["ai_code"]
    assert videos[0]["seed"] == "c1"


async def test_runner_first_layer_pass_makes_no_video(monkeypatch, tmp_path, client, dashboard):
    packet = await packet_for(client, dashboard)
    videos: list = []
    fake_artifacts(monkeypatch, packet, videos)
    runner = ReviewRunner(
        first_layer=make_reviewer(jev_answers()),
        client=object(),  # type: ignore[arg-type]
        settings=runner_settings(tmp_path, video_enabled=True),
    )

    outcome = await runner.review_cert("c1")

    assert outcome.review.verdict == ReviewVerdict.FLAG_FOR_HUMAN
    assert outcome.reject_message is None
    assert outcome.video_path is None and outcome.video_error is None
    assert videos == []


async def test_runner_first_layer_video_failure_keeps_verdict(
    monkeypatch, tmp_path, client, dashboard
):
    packet = await packet_for(client, dashboard)
    fake_artifacts(monkeypatch, packet, [])

    async def broken_video(**kwargs):
        raise RuntimeError("chromium crashed")

    monkeypatch.setattr("clanker.review.runner.generate_reject_video", broken_video)
    runner = ReviewRunner(
        first_layer=make_reviewer(jev_answers(ai_code=0.9)),
        client=object(),  # type: ignore[arg-type]
        settings=runner_settings(tmp_path, video_enabled=True),
    )

    outcome = await runner.review_cert("c1")

    assert outcome.review.verdict == ReviewVerdict.REJECT
    assert outcome.pdf_path is not None
    assert outcome.video_path is None
    assert outcome.video_error == "chromium crashed"


def test_runner_requires_a_reviewer(tmp_path):
    with pytest.raises(ValueError):
        ReviewRunner(client=object(), settings=runner_settings(tmp_path))  # type: ignore[arg-type]


@pytest.mark.skipif(shutil.which("typst") is None, reason="typst not installed")
@pytest.mark.parametrize("scores", [{"ai_readme": 0.95}, {"ai_code": 0.6}])
async def test_first_layer_pdf_compiles(tmp_path, client, dashboard, scores):
    from clanker.review.first_layer.report import build_report_data
    from clanker.review.pdf import generate_first_layer_pdf

    packet = await packet_for(client, dashboard)
    result = await make_reviewer(jev_answers(**scores)).review(packet)
    path = await generate_first_layer_pdf(
        build_report_data(result, packet),
        output_path=tmp_path / "fl.pdf",
        project_name="Test \"Project\" #1 [x]",
        project_desc="Has $pecial *chars* _here_",
        repo_url="https://github.com/x/y",
        demo_url="https://example.com",
        readme_url=RAW_README,
    )
    assert path.read_bytes()[:5] == b"%PDF-"
