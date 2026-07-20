"""Posts ship announcements and review results to Slack.

Consumes ``ReviewOutcome`` from the runner — all Slack formatting lives here and
nowhere else (v1 mixed this into the review orchestration).

The new-ship message is rendered as a Block Kit "embed" (a coloured attachment):
a header, the project name with a project-type badge and a status badge
(``AUTOMATING`` while the review runs, then ``APPROVE`` / ``REJECT`` /
``NEEDS HUMAN``), the description, dev time / submitted date, quick links, and an
optional cc ping. The status badge's colour drives the attachment's left bar.
"""

from __future__ import annotations

import logging
from datetime import datetime

from slack_sdk.web.async_client import AsyncWebClient

from clanker.review import ReviewOutcome
from clanker.review.models import ReviewVerdict
from clanker.shipwrights import CertSummary

logger = logging.getLogger(__name__)

# status label -> (attachment colour, emoji shown with the verdict line)
_AUTOMATING = "AUTOMATING"
_STATUS_STYLE = {
    _AUTOMATING: ("#E2B203", ":robot_face:"),
    "APPROVE": ("#2EB67D", ":bread_nod:"),
    "REJECT": ("#E01E5A", ":no:"),
    "NEEDS HUMAN": ("#8B5CF6", ":aaa:"),
}
_DEFAULT_STYLE = ("#8D8D8D", ":grey_question:")

_VERDICT_LABEL = {
    ReviewVerdict.APPROVE: "APPROVE",
    ReviewVerdict.REJECT: "REJECT",
    ReviewVerdict.FLAG_FOR_HUMAN: "NEEDS HUMAN",
}


def _first_sentence(text: str, limit: int = 240) -> str:
    sentence = text.split(". ")[0].strip()
    if len(sentence) > limit:
        sentence = sentence[:limit] + "…"
    if not sentence.endswith("."):
        sentence += "."
    return sentence


class Announcer:
    def __init__(
        self,
        slack: AsyncWebClient,
        *,
        channel: str,
        dashboard_base_url: str,
        workplace: str,
        ship_ping: str = "",
    ) -> None:
        self._slack = slack
        self._channel = channel
        self._dashboard_base_url = dashboard_base_url.rstrip("/")
        self._workplace = workplace
        self._ship_ping = ship_ping.strip()

    def _cert_link(self, cert_id: str) -> str:
        return f"{self._dashboard_base_url}/{self._workplace}/certifications/{cert_id}"

    def _ping_mrkdwn(self) -> str | None:
        """Render the configured cc target as a Slack mention (or literal text)."""
        ping = self._ship_ping
        if not ping:
            return None
        if ping.startswith("S"):  # usergroup / subteam
            return f"<!subteam^{ping}>"
        if ping[0] in ("U", "W"):  # user
            return f"<@{ping}>"
        return ping

    @staticmethod
    def _submitted_mrkdwn(created_at: datetime | None) -> str:
        if not created_at:
            return "—"
        ts = int(created_at.timestamp())
        fallback = created_at.strftime("%b %d at %I:%M %p").replace(" 0", " ")
        return f"<!date^{ts}^{{date_short_pretty}} at {{time}}|{fallback}>"

    def _ship_attachment(
        self,
        cert: CertSummary,
        *,
        status_label: str,
        verdict_block: dict | None = None,
    ) -> dict:
        """Build the coloured Block Kit attachment for a ship announcement."""
        color, _ = _STATUS_STYLE.get(status_label, _DEFAULT_STYLE)
        ptype = cert.project_type or "?"

        blocks: list[dict] = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{cert.project_name}*  ·  `{ptype}`  ·  `{status_label}`",
                },
            },
        ]
        if cert.description:
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": cert.description.strip()}}
            )

        if verdict_block:
            blocks.append(verdict_block)

        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Dev Time:*\n{cert.dev_time or '—'}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Submitted:*\n{self._submitted_mrkdwn(cert.created_at)}",
                    },
                ],
            }
        )

        link_parts = [f"<{self._cert_link(cert.id)}|#{cert.external_id or '?'}>"]
        if cert.demo_url:
            link_parts.append(f"<{cert.demo_url}|Demo>")
        if cert.repo_url:
            link_parts.append(f"<{cert.repo_url}|Repo>")
        if cert.readme_url:
            link_parts.append(f"<{cert.readme_url}|README>")
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": "  ·  ".join(link_parts)}]}
        )

        # NOTE: the cc ping deliberately does NOT live in the embed. The embed is
        # the thread parent for the running note / PDF / video, so a mention here
        # would make the pinged user follow the thread and get re-notified for
        # every one of those replies. The ping goes on a separate standalone
        # message instead (see ``announce_ship``).
        return {"color": color, "blocks": blocks, "fallback": self._fallback_text(cert)}

    @staticmethod
    def _fallback_text(cert: CertSummary) -> str:
        return f"New ship: {cert.project_name} ({cert.project_type or '?'})"

    def _verdict_block(self, outcome: ReviewOutcome) -> dict | None:
        review = outcome.review
        _, emoji = _STATUS_STYLE.get(_VERDICT_LABEL.get(review.verdict, ""), _DEFAULT_STYLE)
        parts: list[str] = []
        if review.reasoning:
            parts.append(f"{emoji} {_first_sentence(review.reasoning)}")
        if review.special_flags:
            parts.append(f":triangular_flag_on_post: {', '.join(review.special_flags)}")
        if not parts:
            return None
        return {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(parts)}}

    async def announce_online(self, poll_interval: float) -> None:
        try:
            await self._slack.chat_postMessage(
                channel=self._channel,
                text=f"I am alive..",
            )
        except Exception:
            logger.exception("Failed to send online announcement")

    async def announce_ship(self, cert: CertSummary) -> str:
        """Post the ping headline + a separate embed; returns the embed's ts.

        Two separate top-level messages, on purpose:

        1. A plain-text headline (``New ship: …``) that carries the group ping.
           It is standalone — nothing is ever threaded under it — so the mention
           notifies the target exactly once and never re-fires.
        2. The coloured embed, with NO mention. This is the thread parent for the
           running note, PDF, and video, so those replies don't re-ping anyone.
        """
        headline = self._fallback_text(cert)
        headline_blocks: list[dict] = [
            {"type": "section", "text": {"type": "mrkdwn", "text": headline}}
        ]
        if ping := self._ping_mrkdwn():
            # A context block is Slack's smallest text style; the mention inside
            # it still notifies the target.
            headline_blocks.append(
                {"type": "context", "elements": [{"type": "mrkdwn", "text": f"cc {ping}"}]}
            )
        await self._slack.chat_postMessage(
            channel=self._channel, text=headline, blocks=headline_blocks
        )

        post = await self._slack.chat_postMessage(
            channel=self._channel,
            attachments=[self._ship_attachment(cert, status_label=_AUTOMATING)],
        )
        ts: str = post["ts"]
        await self._slack.chat_postMessage(
            channel=self._channel,
            thread_ts=ts,
            text=":Running the automated review..",
        )
        return ts

    async def post_outcome(self, cert: CertSummary, outcome: ReviewOutcome, parent_ts: str) -> None:
        """Update the embed with the verdict, then upload every available artifact."""
        status_label = _VERDICT_LABEL.get(outcome.review.verdict, "NEEDS HUMAN")
        try:
            await self._slack.chat_update(
                channel=self._channel,
                ts=parent_ts,
                attachments=[
                    self._ship_attachment(
                        cert,
                        status_label=status_label,
                        verdict_block=self._verdict_block(outcome),
                    )
                ],
            )
        except Exception:
            logger.exception("Failed to update parent message with verdict")

        if outcome.pdf_path:
            await self._slack.files_upload_v2(
                channel=self._channel,
                thread_ts=parent_ts,
                file=str(outcome.pdf_path),
                filename="review_report.pdf",
                initial_comment="done",
            )
        else:
            await self._slack.chat_postMessage(
                channel=self._channel,
                thread_ts=parent_ts,
                text="Review finished but the PDF report failed to generate.",
            )

        if outcome.video_path:
            await self._slack.files_upload_v2(
                channel=self._channel,
                thread_ts=parent_ts,
                file=str(outcome.video_path),
                filename="review_walkthrough.mp4",
                initial_comment="vid",
            )
        elif outcome.video_error:
            await self._slack.chat_postMessage(
                channel=self._channel,
                thread_ts=parent_ts,
                text="Review video generation failed; the verdict and PDF are unaffected.",
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
