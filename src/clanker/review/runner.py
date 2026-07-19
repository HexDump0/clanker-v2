"""Orchestrates one review: packet -> agent -> structured result -> PDF.

Pure pipeline — no Slack in here (the slack layer consumes ReviewOutcome), no
contextvars (the cert id is passed explicitly end to end), no message-log
scraping (the verdict is the agent's validated output).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent

from clanker.config import Settings
from clanker.review.models import ReviewOutput
from clanker.review.packet import ReviewPacket, build_packet
from clanker.review.pdf import PdfError, generate_review_pdf
from clanker.review.tools import ReviewTools
from clanker.shipwrights import ShipwrightsClient

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReviewOutcome:
    cert_id: str
    packet: ReviewPacket
    review: ReviewOutput
    pdf_path: Path | None
    input_tokens: int
    output_tokens: int


class ReviewRunner:
    def __init__(
        self,
        *,
        agent: Agent[None, ReviewOutput],
        client: ShipwrightsClient,
        settings: Settings,
        tools: ReviewTools | None = None,
    ) -> None:
        self._agent = agent
        self._client = client
        self._settings = settings
        self._tools = tools

    async def review_cert(self, cert_id: str) -> ReviewOutcome:
        """Run the full pipeline for one cert. Raises on unrecoverable errors."""
        packet = await build_packet(self._client, cert_id, tools=self._tools)
        logger.info("Reviewing cert %s (%r)", cert_id, packet.cert.project_name)

        result = await self._agent.run(packet.to_prompt())
        review = result.output
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

        pdf_path: Path | None = None
        try:
            pdf_path = await generate_review_pdf(
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

        return ReviewOutcome(
            cert_id=cert_id,
            packet=packet,
            review=review,
            pdf_path=pdf_path,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
