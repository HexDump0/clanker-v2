"""Orchestrates one review: packet -> reviewer -> structured result -> PDF (+ video).

The reviewer is either the first layer (code checks + one Jev call; REJECT or PASS to a
human) or the older DeepSeek review agent, chosen by ``Settings.review_mode``.

Pure pipeline — no Slack in here (the slack layer consumes ReviewOutcome), no
contextvars (the cert id is passed explicitly end to end), no message-log
scraping (the verdict is the agent's validated output).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent

from clanker.config import Settings
from clanker.results import ResultStore
from clanker.review.first_layer import FirstLayerResult, FirstLayerReviewer, to_review_output
from clanker.review.first_layer.report import build_report_data
from clanker.review.models import ReviewOutput, ReviewVerdict
from clanker.review.packet import ReviewPacket, build_packet
from clanker.review.pdf import PdfError, generate_first_layer_pdf, generate_review_pdf
from clanker.review.tools import ReviewTools
from clanker.review.video.compositor import DEFAULT_MUSIC
from clanker.review.video.director import Director
from clanker.review.video.models import VideoProject
from clanker.review.video.pipeline import (
    VideoGenerationResult,
    generate_reject_video,
    generate_review_video,
)
from clanker.review.video.template_director import plan_scenes
from clanker.shipwrights import ShipwrightsClient

logger = logging.getLogger(__name__)


class PrivateContextLeakError(RuntimeError):
    """The model copied private reviewer notes into public review output."""


def _guard_private_context(review: ReviewOutput, private_values: list[str]) -> None:
    """Block artifacts when a meaningful private-note phrase is copied verbatim."""
    public = re.sub(
        r"\s+",
        " ",
        json.dumps(review.model_dump(mode="json"), ensure_ascii=False).lower(),
    )
    for value in private_values:
        normalized = re.sub(r"\s+", " ", value).strip().lower()
        candidates = [normalized]
        candidates.extend(
            re.sub(r"\s+", " ", part).strip().lower() for part in re.split(r"[\n.!?]+", value)
        )
        leaked = next((part for part in candidates if len(part) >= 24 and part in public), None)
        if leaked:
            raise PrivateContextLeakError(
                "review output copied private Dashboard notes; public artifacts were blocked"
            )


@dataclass(slots=True)
class ReviewOutcome:
    cert_id: str
    packet: ReviewPacket
    review: ReviewOutput
    pdf_path: Path | None
    input_tokens: int
    output_tokens: int
    video_path: Path | None = None
    video_error: str | None = None
    # First-layer only: the copy-ready message for the shipper on REJECT.
    reject_message: str | None = None
    first_layer: FirstLayerResult | None = None


class ReviewRunner:
    def __init__(
        self,
        *,
        client: ShipwrightsClient,
        settings: Settings,
        agent: Agent[None, ReviewOutput] | None = None,
        first_layer: FirstLayerReviewer | None = None,
        tools: ReviewTools | None = None,
        video_director: Director | None = None,
    ) -> None:
        if agent is None and first_layer is None:
            raise ValueError("ReviewRunner needs a review agent or a first-layer reviewer")
        self._agent = agent
        self._first_layer = first_layer
        self._client = client
        self._settings = settings
        self._tools = tools
        self._video_director = video_director

    def _resolve_video_music(self) -> Path | None:
        """The music track to mix in: configured file, bundled default, or none."""
        if not self._settings.video_music_enabled:
            return None
        return self._settings.video_music_file or DEFAULT_MUSIC

    async def review_cert(self, cert_id: str) -> ReviewOutcome:
        """Run the full pipeline for one cert. Raises on unrecoverable errors."""
        packet = await build_packet(self._client, cert_id, tools=self._tools)
        logger.info("Reviewing cert %s (%r)", cert_id, packet.cert.project_name)
        if self._first_layer is not None:
            outcome = await self._review_first_layer(cert_id, packet, self._first_layer)
        else:
            outcome = await self._review_with_agent(cert_id, packet)
        try:
            ResultStore(self._settings.results_dir).save_outcome(outcome)
        except Exception:
            # The browser extension's record is a convenience; never fail a review over it.
            logger.exception("Could not save result for cert %s", cert_id)
        return outcome

    async def _render_pdf(
        self, cert_id: str, packet: ReviewPacket, review: ReviewOutput
    ) -> Path | None:
        try:
            return await generate_review_pdf(
                review,
                output_path=self._settings.pdf_dir / f"{cert_id}.pdf",
                project_name=packet.cert.project_name,
                project_desc=packet.cert.description or "",
                repo_url=packet.cert.repo_url,
                demo_url=packet.cert.demo_url,
            )
        except PdfError:
            # The verdict is still valid without the report.
            logger.exception("PDF generation failed for cert %s", cert_id)
            return None

    async def _video_stage(
        self, cert_id: str, make: Callable[[], Awaitable[VideoGenerationResult]]
    ) -> tuple[Path | None, str | None]:
        """Run one optional video job under the timeout; failures never touch the verdict."""
        try:
            generated = await asyncio.wait_for(make(), timeout=self._settings.video_timeout)
            return generated.video.path, None
        except TimeoutError:
            logger.exception("Video generation timed out for cert %s", cert_id)
            return None, f"video generation exceeded the {self._settings.video_timeout:g}s timeout"
        except Exception as exc:
            # A failed optional artifact never invalidates the review or PDF.
            logger.exception("Video generation failed for cert %s", cert_id)
            return None, str(exc)

    async def _review_first_layer(
        self, cert_id: str, packet: ReviewPacket, reviewer: FirstLayerReviewer
    ) -> ReviewOutcome:
        result = await reviewer.review(packet)
        review = to_review_output(result)
        pdf_path: Path | None = None
        try:
            pdf_path = await generate_first_layer_pdf(
                build_report_data(result, packet),
                output_path=self._settings.pdf_dir / f"{cert_id}.pdf",
                project_name=packet.cert.project_name,
                project_desc=packet.cert.description or "",
                repo_url=packet.cert.repo_url,
                demo_url=packet.cert.demo_url,
                readme_url=packet.cert.readme_url,
                project_url=packet.stardance_url,
            )
        except PdfError:
            logger.exception("PDF generation failed for cert %s", cert_id)

        video_path: Path | None = None
        video_error: str | None = None
        if (
            self._settings.video_enabled
            and review.verdict == ReviewVerdict.REJECT
            # Reasons with nothing to show (e.g. an unsupported repo host) mean no video,
            # not a failed one.
            and plan_scenes(result.reasons, result.video_inputs, cert_id)
        ):
            video_path, video_error = await self._video_stage(
                cert_id,
                lambda: generate_reject_video(
                    reasons=result.reasons,
                    inputs=result.video_inputs,
                    seed=cert_id,
                    work_dir=self._settings.video_work_dir / cert_id,
                    output_path=self._settings.video_dir / f"{cert_id}.mp4",
                    music_path=self._resolve_video_music(),
                ),
            )

        return ReviewOutcome(
            cert_id=cert_id,
            packet=packet,
            review=review,
            pdf_path=pdf_path,
            input_tokens=result.jev_input_tokens,
            output_tokens=0,
            video_path=video_path,
            video_error=video_error,
            reject_message=result.message,
            first_layer=result,
        )

    async def _review_with_agent(self, cert_id: str, packet: ReviewPacket) -> ReviewOutcome:
        assert self._agent is not None
        result = await self._agent.run(packet.to_prompt())
        review = result.output
        _guard_private_context(review, getattr(packet, "private_context", []))
        usage = result.usage
        logger.info(
            "Cert %s verdict: %s (%s) | tokens: %d in / %d out / %d requests",
            cert_id,
            review.verdict.value,
            review.project_type,
            usage.input_tokens,
            usage.output_tokens,
            usage.requests,
        )

        pdf_path = await self._render_pdf(cert_id, packet, review)

        video_path: Path | None = None
        video_error: str | None = None
        if (
            self._settings.video_enabled
            and self._video_director is not None
            and review.video_evidence
        ):
            director = self._video_director
            video_path, video_error = await self._video_stage(
                cert_id,
                lambda: generate_review_video(
                    project=VideoProject(
                        project_name=packet.cert.project_name,
                        project_author=(
                            packet.cert.submitter_username or packet.cert.submitter_name or ""
                        ),
                        verdict=review.verdict.value,
                        required_fixes=review.required_fixes or [],
                    ),
                    evidence=review.video_evidence,
                    director=director,
                    work_dir=self._settings.video_work_dir / cert_id,
                    output_path=self._settings.video_dir / f"{cert_id}.mp4",
                    music_path=self._resolve_video_music(),
                ),
            )

        return ReviewOutcome(
            cert_id=cert_id,
            packet=packet,
            review=review,
            pdf_path=pdf_path,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            video_path=video_path,
            video_error=video_error,
        )
