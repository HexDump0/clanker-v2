"""Posts ship announcements and review results to Slack.

Consumes ``ReviewOutcome`` from the runner — all Slack formatting lives here and
nowhere else (v1 mixed this into the review orchestration).
"""

from __future__ import annotations

import logging

from slack_sdk.web.async_client import AsyncWebClient

from clanker.review import ReviewOutcome
from clanker.review.models import ReviewVerdict
from clanker.shipwrights import CertSummary

logger = logging.getLogger(__name__)

VERDICT_EMOJI = {
    ReviewVerdict.APPROVE: ":bread_nod:",
    ReviewVerdict.REJECT: ":no:",
    ReviewVerdict.FLAG_FOR_HUMAN: ":aaa:",
}


def _first_sentence(text: str, limit: int = 200) -> str:
    sentence = text.split(". ")[0].strip()
    if len(sentence) > limit:
        sentence = sentence[:limit] + "…"
    if not sentence.endswith("."):
        sentence += "."
    return sentence


class Announcer:
    def __init__(self, slack: AsyncWebClient, *, channel: str, dashboard_base_url: str,
                 workplace: str) -> None:
        self._slack = slack
        self._channel = channel
        self._dashboard_base_url = dashboard_base_url.rstrip("/")
        self._workplace = workplace

    def _cert_link(self, cert_id: str) -> str:
        return f"{self._dashboard_base_url}/{self._workplace}/certifications/{cert_id}"

    def ship_text(self, cert: CertSummary) -> str:
        lines = [f"*New ship!!* :yay:  \n {cert.project_name} · {cert.project_type or '?'}"]
        submitter = cert.submitter_username or cert.submitter_name
        if submitter:
            lines.append(f"by {submitter}")
        lines.append(f"<{self._cert_link(cert.id)}|open in dashboard>")
        return "\n".join(lines)

    async def announce_online(self, poll_interval: float) -> None:
        try:
            await self._slack.chat_postMessage(
                channel=self._channel,
                text=f":shipitparrot: Watching for new ships! Polling every {int(poll_interval)}s",
            )
        except Exception:
            logger.exception("Failed to send online announcement")

    async def announce_ship(self, cert: CertSummary) -> str:
        """Post the new-ship message + threaded status note; returns the parent ts."""
        post = await self._slack.chat_postMessage(channel=self._channel, text=self.ship_text(cert))
        ts: str = post["ts"]
        await self._slack.chat_postMessage(
            channel=self._channel,
            thread_ts=ts,
            text=":think: Running the automated review, this might take a few minutes…",
        )
        return ts

    async def post_outcome(self, cert: CertSummary, outcome: ReviewOutcome, parent_ts: str) -> None:
        """Edit the parent with the verdict and upload the PDF to the thread."""
        review = outcome.review
        emoji = VERDICT_EMOJI.get(review.verdict, ":grey_question:")
        text = self.ship_text(cert) + f"\n\n{emoji} *{review.verdict.value}*"
        if review.reasoning:
            text += f"\n{_first_sentence(review.reasoning)}"
        if review.special_flags:
            text += f"\n:triangular_flag_on_post: {', '.join(review.special_flags)}"
        try:
            await self._slack.chat_update(channel=self._channel, ts=parent_ts, text=text)
        except Exception:
            logger.exception("Failed to update parent message with verdict")

        if outcome.pdf_path:
            await self._slack.files_upload_v2(
                channel=self._channel,
                thread_ts=parent_ts,
                file=str(outcome.pdf_path),
                filename="review_report.pdf",
                initial_comment=":thumbup-nobg: Review complete!",
            )
        else:
            await self._slack.chat_postMessage(
                channel=self._channel,
                thread_ts=parent_ts,
                text="Review finished but the PDF report failed to generate.",
            )

    async def post_failure(self, parent_ts: str) -> None:
        try:
            await self._slack.chat_postMessage(
                channel=self._channel,
                thread_ts=parent_ts,
                text=":explode: Review failed — check the logs.",
            )
        except Exception:
            logger.exception("Failed to post failure message")
