from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from clanker.review.models import ReviewVerdict
from clanker.review.runner import ReviewOutcome
from clanker.shipwrights import CertSummary
from clanker.slack.announcer import Announcer
from tests.conftest import make_cert
from tests.test_review import make_review


def make_announcer() -> tuple[Announcer, AsyncMock]:
    slack = AsyncMock()
    slack.chat_postMessage.return_value = {"ts": "111.222"}
    announcer = Announcer(
        slack,
        channel="C123",
        dashboard_base_url="https://ds.shipwrights.dev",
        workplace="stardance",
    )
    return announcer, slack


def outcome_for(
    cert: CertSummary,
    pdf: Path | None = None,
    video: Path | None = None,
    **review_overrides,
) -> ReviewOutcome:
    return ReviewOutcome(
        cert_id=cert.id,
        packet=None,  # not used by the announcer
        review=make_review(**review_overrides),
        pdf_path=pdf,
        input_tokens=100,
        output_tokens=50,
        video_path=video,
    )


async def test_announce_ship_posts_parent_and_thread():
    announcer, slack = make_announcer()
    cert = CertSummary.model_validate(make_cert("c1"))
    ts = await announcer.announce_ship(cert)
    assert ts == "111.222"
    assert slack.chat_postMessage.call_count == 2
    parent_text = slack.chat_postMessage.call_args_list[0].kwargs["text"]
    assert "Project c1" in parent_text
    assert "ds.shipwrights.dev/stardance/certifications/c1" in parent_text


async def test_post_outcome_updates_parent_and_uploads_pdf(tmp_path):
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-fake")
    announcer, slack = make_announcer()
    cert = CertSummary.model_validate(make_cert("c1"))

    await announcer.post_outcome(
        cert,
        outcome_for(cert, pdf=pdf, verdict=ReviewVerdict.REJECT, special_flags=["AI UNDISCLOSED"]),
        parent_ts="111.222",
    )
    updated = slack.chat_update.call_args.kwargs["text"]
    assert "*REJECT*" in updated
    assert "AI UNDISCLOSED" in updated
    slack.files_upload_v2.assert_awaited_once()
    assert slack.files_upload_v2.call_args.kwargs["thread_ts"] == "111.222"


async def test_post_outcome_without_pdf_posts_note():
    announcer, slack = make_announcer()
    cert = CertSummary.model_validate(make_cert("c1"))
    await announcer.post_outcome(cert, outcome_for(cert, pdf=None), parent_ts="111.222")
    slack.files_upload_v2.assert_not_awaited()
    note = slack.chat_postMessage.call_args.kwargs["text"]
    assert "PDF report failed" in note


async def test_post_outcome_uploads_pdf_and_video(tmp_path):
    pdf = tmp_path / "r.pdf"
    video = tmp_path / "r.mp4"
    pdf.write_bytes(b"%PDF-fake")
    video.write_bytes(b"mp4")
    announcer, slack = make_announcer()
    cert = CertSummary.model_validate(make_cert("c1"))

    await announcer.post_outcome(cert, outcome_for(cert, pdf=pdf, video=video), "111.222")

    assert slack.files_upload_v2.await_count == 2
    uploads = slack.files_upload_v2.call_args_list
    assert uploads[0].kwargs["filename"] == "review_report.pdf"
    assert uploads[1].kwargs["filename"] == "review_walkthrough.mp4"
