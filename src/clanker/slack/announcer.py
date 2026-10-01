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

from clanker.daily import DailyStats, daily_fallback_text
from clanker.review import ReviewOutcome
from clanker.review.models import ReviewVerdict
from clanker.shipwrights import CertSummary
from clanker.stardance import AdminShip

logger = logging.getLogger(__name__)

# status label -> (attachment colour, emoji shown with the verdict line)
_AUTOMATING = "AUTOMATING"
_STATUS_STYLE = {
    _AUTOMATING: ("#E2B203", ":robot_face:"),
    "APPROVE": ("#2EB67D", ":bread_nod:"),
    "REJECT": ("#E01E5A", ":no:"),
    "NEEDS HUMAN": ("#8B5CF6", ":aaa:"),
    "DASH DOWN": ("#E01E5A", ":rotating_light:"),
}
_DEFAULT_STYLE = ("#8D8D8D", ":grey_question:")
_DAILY_COLOR = "#6D28D9"

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
        daily_ping: str = "",
        reject_ping: str = "",
    ) -> None:
        self._slack = slack
        self._channel = channel
        self._dashboard_base_url = dashboard_base_url.rstrip("/")
        self._workplace = workplace
        self._ship_ping = ship_ping.strip()
        self._daily_ping = daily_ping.strip()
        self._reject_ping = reject_ping.strip()

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

    def _daily_ping_mrkdwn(self) -> str | None:
        ping = self._daily_ping
        if not ping:
            return None
        if ping.startswith("S"):
            return f"<!subteam^{ping}>"
        if ping[0] in ("U", "W"):
            return f"<@{ping}>"
        return ping

    def _reject_ping_mrkdwn(self) -> str | None:
        ping = self._reject_ping
        if not ping:
            return None
        if ping.startswith("S"):
            return f"<!subteam^{ping}>"
        if ping[0] in ("U", "W"):
            return f"<@{ping}>"
        return ping

    @staticmethod
    def _reviewer_ping(entry) -> str:
        """Slack mention for a leaderboard entry (memberId is ``s:U...``)."""
        member_id = entry.member_id or ""
        slack_id = member_id.split(":", 1)[1] if ":" in member_id else member_id
        if slack_id.startswith(("U", "W")):
            return f"<@{slack_id}>"
        return entry.name or entry.member_id or "nobody"

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
                text=":hii:",
            )
        except Exception:
            logger.exception("Failed to send online announcement")

    async def announce_daily_summary(self, stats: DailyStats) -> None:
        """Post the 23:30 UTC queue digest as a single embed.

        This message is standalone (nothing is ever threaded under it), so unlike
        the ship announcements the cc ping can live inside the embed itself —
        the mention fires exactly once.
        """
        blocks: list[dict] = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*Daily Queue Stats*\n"
                        "Hello meatbags :hello: , here's todays stats\n"
                        f"- {stats.pending} projects currently pending.\n"
                        f"- {stats.era5} projects have entered the 5d era.\n"
                        f"- {stats.reviewed_today} projects reviewed today."
                    ),
                },
            }
        ]

        if stats.oldest:
            look = ["*Some projects you need to look at:*"]
            for cert in stats.oldest:
                ptype = cert.ai_type or cert.project_type or "?"
                look.append(f"• <{self._cert_link(cert.id)}|{cert.project_name}> ({ptype})")
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(look)}})
        else:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Some projects you need to look at:*\nThe queue is "
                        "empty. Statistically impossible. Enjoy it, meatbags.",
                    },
                }
            )

        if stats.best is not None:
            best_text = (
                f"And the best shipwright of today is {self._reviewer_ping(stats.best)} :yay2:"
            )
            if stats.praise:
                best_text += f"\n{stats.praise}"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": best_text}})

        if ping := self._daily_ping_mrkdwn():
            blocks.append(
                {"type": "context", "elements": [{"type": "mrkdwn", "text": f"cc: {ping}"}]}
            )

        try:
            await self._slack.chat_postMessage(
                channel=self._channel,
                # No top-level `text`: with legacy attachments Slack renders it
                # as a second message body above the embed. The attachment's
                # own `fallback` covers notifications/unfurl clients.
                attachments=[
                    {
                        "color": _DAILY_COLOR,
                        "blocks": blocks,
                        "fallback": daily_fallback_text(stats),
                    }
                ],
            )
        except Exception:
            logger.exception("Failed to post the daily summary")

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
            text="Running the automated review..",
        )
        return ts

    async def announce_review_request(
        self, cert: CertSummary, *, rereview: bool, requested_by: str | None = None
    ) -> str:
        """A review someone asked for from the browser extension; returns the thread parent ts.

        One message, no ping: the original ship was already announced (or the person asking
        is a reviewer already looking at it), so nobody is re-notified.
        """
        label = "Re-review requested" if rereview else "Review requested"
        attachment = self._ship_attachment(cert, status_label=_AUTOMATING)
        attachment["fallback"] = f"{label}: {cert.project_name}"
        post = await self._slack.chat_postMessage(channel=self._channel, attachments=[attachment])
        ts: str = post["ts"]
        await self._slack.chat_postMessage(
            channel=self._channel,
            thread_ts=ts,
            text=(
                f"{label}{f' by {requested_by}' if requested_by else ''} from the browser "
                "extension. Running the automated review.."
            ),
        )
        return ts

    async def post_manual_review(
        self,
        cert_id: str,
        project_name: str,
        *,
        parent_ts: str | None,
        note: str,
        wrong_reasons: list[str],
        by: str | None = None,
    ) -> None:
        """A human marked Clanker's review wrong: ask the reviewers to do this one by hand."""
        lines = [
            ":rotating_light: *Clanker got this one wrong, please review manually.* "
            f"<{self._cert_link(cert_id)}|{project_name}>" + (f" (marked by {by})" if by else "")
        ]
        if wrong_reasons:
            lines.append("Marked wrong: " + ", ".join(wrong_reasons))
        if note:
            lines.append(f"> {note}")
        if ping := self._ping_mrkdwn():
            lines.append(f"cc {ping}")
        await self._slack.chat_postMessage(
            channel=self._channel, thread_ts=parent_ts, text="\n".join(lines)
        )

    def _stardance_attachment(
        self,
        ship: AdminShip,
        *,
        ship_url: str,
        status_label: str,
    ) -> dict:
        """Embed for a ship announced straight from Stardance, pre-Dashboard.

        The Stardance admin ship page stands in for the Dashboard link until
        the ship is imported (the admin page itself redirects once it is).
        """
        color, _ = _STATUS_STYLE.get(status_label, _DEFAULT_STYLE)
        ptype = ship.project_type or "?"

        blocks: list[dict] = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{ship.title or ship.ship_id}*  ·  `{ptype}`  ·  `{status_label}`",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Author:*\n{ship.author or '—'}"},
                    {"type": "mrkdwn", "text": f"*In queue:*\n{ship.wait or '—'}"},
                ],
            },
        ]

        link_parts = [f"<{ship_url}|#{ship.ship_id}>"]
        if ship.demo_url:
            link_parts.append(f"<{ship.demo_url}|Demo>")
        if ship.repo_url:
            link_parts.append(f"<{ship.repo_url}|Repo>")
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": "  ·  ".join(link_parts)}]}
        )
        return {
            "color": color,
            "blocks": blocks,
            "fallback": f"New ship: {ship.title or ship.ship_id} ({ptype})",
        }

    async def announce_ship_from_stardance(self, ship: AdminShip, *, ship_url: str) -> str:
        """Announce a ship the instant Stardance shows it, pre-reconciliation.

        Same two-message structure as ``announce_ship``; returns the embed ts
        so the review result can later land in the same thread.
        """
        headline = f"New ship: {ship.title or ship.ship_id} ({ship.project_type or '?'})"
        headline_blocks: list[dict] = [
            {"type": "section", "text": {"type": "mrkdwn", "text": headline}}
        ]
        if ping := self._ping_mrkdwn():
            headline_blocks.append(
                {"type": "context", "elements": [{"type": "mrkdwn", "text": f"cc {ping}"}]}
            )
        await self._slack.chat_postMessage(
            channel=self._channel, text=headline, blocks=headline_blocks
        )
        post = await self._slack.chat_postMessage(
            channel=self._channel,
            attachments=[
                self._stardance_attachment(ship, ship_url=ship_url, status_label=_AUTOMATING)
            ],
        )
        ts: str = post["ts"]
        await self._slack.chat_postMessage(
            channel=self._channel,
            thread_ts=ts,
            text="Running the automated review..",
        )
        return ts

    async def announce_dash_down(
        self, ship: AdminShip, *, ship_url: str, parent_ts: str | None
    ) -> None:
        """Report that a detected ship will not be reviewed: Dashboard unreachable.

        Flips the embed badge to ``DASH DOWN`` and posts the crash note in the
        announcement thread so the thread no longer claims a review is running.
        """
        if parent_ts:
            try:
                await self._slack.chat_update(
                    channel=self._channel,
                    ts=parent_ts,
                    attachments=[
                        self._stardance_attachment(
                            ship, ship_url=ship_url, status_label="DASH DOWN"
                        )
                    ],
                )
            except Exception:
                logger.exception("Failed to flip ship embed to DASH DOWN")
            try:
                await self._slack.chat_postMessage(
                    channel=self._channel,
                    thread_ts=parent_ts,
                    text=(
                        ":rotating_light: dash crash — the Shipwrights Dashboard "
                        "did not pick up this ship (retried once after 10s). "
                        "Automated review skipped."
                    ),
                )
            except Exception:
                logger.exception("Failed to post dash-crash message")
        else:
            logger.error(
                "dash crash: ship %s (%s) not imported by Dashboard — review skipped",
                ship.ship_id,
                ship_url,
            )

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

        # When the AI rejects a project, ping the configured role/user in the
        # thread where the PDF/video are posted so reviewers can act quickly.
        if outcome.review.verdict == ReviewVerdict.REJECT:
            if ping := self._reject_ping_mrkdwn():
                try:
                    await self._slack.chat_postMessage(
                        channel=self._channel,
                        thread_ts=parent_ts,
                        text=ping,
                    )
                except Exception:
                    logger.exception("Failed to post reject ping for cert %s", cert.id)

        if outcome.reject_message:
            # Template-written (no LLM) and copy-ready; a human sends it from the
            # dashboard — clanker never calls the mutating reject endpoint.
            try:
                await self._slack.chat_postMessage(
                    channel=self._channel,
                    thread_ts=parent_ts,
                    text=f"Reject message:\n```{outcome.reject_message}```",
                )
            except Exception:
                logger.exception("Failed to post reject message for cert %s", cert.id)

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
