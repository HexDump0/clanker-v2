from __future__ import annotations

import shutil

import pytest

from clanker.config import Settings
from clanker.review.agent import build_model_settings, build_review_instructions
from clanker.review.models import (
    CheckResult,
    ChecksResult,
    CheckStatus,
    ReviewOutput,
    ReviewVerdict,
)
from clanker.review.packet import build_packet
from clanker.review.pdf import generate_review_pdf
from tests.conftest import make_cert


def make_checks(**overrides: CheckResult) -> ChecksResult:
    default = CheckResult(status=CheckStatus.PASS, details="ok")
    fields = {name: default for name in ChecksResult.model_fields}
    fields.update(overrides)
    return ChecksResult(**fields)


def make_review(**overrides) -> ReviewOutput:
    kwargs = dict(
        verdict=ReviewVerdict.APPROVE,
        project_type="Web App",
        checks=make_checks(),
        reasoning="All checks passed. The project is solid.",
    )
    kwargs.update(overrides)
    return ReviewOutput(**kwargs)


def test_checks_as_pdf_rows_covers_full_rubric():
    rows = make_checks(
        demo_validity=CheckResult(status=CheckStatus.FAIL, details="demo is a Drive link")
    ).as_pdf_rows()
    assert len(rows) == 13
    by_name = {r["name"]: r for r in rows}
    assert by_name["demo_validity"]["status"] == "fail"
    assert by_name["pre_event_commits"]["status"] == "pass"


async def test_build_packet_prompt(client, dashboard):
    dashboard.details["c1"] = {
        **make_cert("c1"),
        "aiDeclaration": "Used Copilot for boilerplate",
        "reviews": [
            {
                "id": "r1",
                "certId": "c1",
                "verdict": "REJECTED",
                "comment": "README too thin",
                "createdAt": "2026-07-01T00:00:00.000Z",
            }
        ],
    }
    packet = await build_packet(client, "c1")
    prompt = packet.to_prompt()
    assert "cert id: c1" in prompt
    assert "Used Copilot for boilerplate" in prompt
    assert "REJECTED: README too thin" in prompt
    assert "# Hi" in prompt  # cached README included


@pytest.mark.skipif(shutil.which("typst") is None, reason="typst not installed")
async def test_generate_pdf(tmp_path):
    review = make_review(
        verdict=ReviewVerdict.REJECT,
        required_fixes=["Add a real README"],
        special_flags=["AI UNDISCLOSED"],
    )
    path = await generate_review_pdf(
        review,
        output_path=tmp_path / "out.pdf",
        project_name="Test Project",
        project_desc="A test",
        repo_url="https://github.com/x/y",
        demo_url="https://example.com",
    )
    assert path.exists()
    assert path.read_bytes()[:5] == b"%PDF-"


def test_review_instructions_reference_real_tools():
    text = build_review_instructions()
    # every tool named in the prompts must exist on the toolset (v1 pain point #11)
    import re

    from clanker.review.tools import ReviewTools

    tools = ReviewTools()
    tool_names = {fn.__name__ for fn in tools.all()}
    referenced = set(re.findall(r"review_[a-z_]+", text))
    assert referenced <= tool_names, f"prompt references unknown tools: {referenced - tool_names}"
    assert "review_generate_pdf" not in text


def test_provider_pin_only_for_openrouter():
    base = dict(shipwrights_session="x", openrouter_api_key="k", hackclub_api_key="h")
    pinned = build_model_settings(
        Settings(**base, openrouter_provider_only="alibaba, cerebras")
    )
    assert pinned["openrouter_provider"] == {
        "only": ["alibaba", "cerebras"],
        "allow_fallbacks": False,
    }

    unpinned = build_model_settings(Settings(**base))
    assert "openrouter_provider" not in unpinned

    hackclub = build_model_settings(
        Settings(**base, ai_provider="hackclub", openrouter_provider_only="alibaba")
    )
    assert "openrouter_provider" not in hackclub
