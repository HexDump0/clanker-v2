"""First-layer review: code facts + one Jev call -> REJECT (with a human-style message) or PASS.

No LLM writes anything here. Jev (a typed-decision model) answers fixed yes/no questions,
code applies the thresholds and hard rules, and the rejection message comes from templates
(``clanker.review.reject_message``). PASS means "a human tests the demo next", not approval.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

from clanker.config import Settings
from clanker.review.first_layer.ai_css import REJECT_AT as AI_CSS_REJECT_AT
from clanker.review.first_layer.evidence import (
    create_banner_agent,
    gather_evidence,
    submission_commit,
)
from clanker.review.first_layer.facts import build_jev_state
from clanker.review.first_layer.facts import field as packet_field
from clanker.review.first_layer.rules import (
    DEFAULT_THRESHOLDS,
    REASONS,
    build_reject_questions,
    reject_decision,
)
from clanker.review.models import (
    CheckResult,
    ChecksResult,
    CheckStatus,
    ReviewOutput,
    ReviewVerdict,
)
from clanker.review.packet import ReviewPacket
from clanker.review.reject_message import RejectContext, compose_reject_message
from clanker.review.video.template_director import RejectVideoInputs

logger = logging.getLogger(__name__)

OPENROUTER_TYPESAFE_BASE = "https://openrouter.ai/api"

# Short labels for Slack/CLI summaries and PDF check details.
REASON_LABELS = {
    "ai_code": "AI-heavy code",
    "ai_readme": "AI-written README",
    "readme_thin": "thin README",
    "readme_not_raw": "README link not raw",
    "no_readme": "no README",
    "bad_hosting": "disallowed demo hosting",
    "demo_broken": "demo doesn't load",
    "demo_is_video": "demo is a video",
    "demo_is_repo": "demo is the repo",
    "missing_build": "no release build",
    "itch_no_build": "no build on itch.io",
    "bot_link_invalid": "bot link isn't a channel/invite",
    "banner_bad": "banner doesn't show the project",
    "banner_default": "no banner",
    "no_source": "no source code",
    "untitled": "untitled project",
    "needs_api_key": "needs the reviewer's own API key",
    "ai_undeclared": "undeclared AI use",
    "feedback_ignored": "previous feedback not addressed",
    "not_eligible": "not eligible",
    "demo_not_testable": "demo can't be tried",
}
PROJECT_TYPE_LABELS = {
    "web_app": "Web App",
    "desktop_app": "Desktop App",
    "cli_tool": "CLI Tool",
    "library": "Library",
    "api": "API",
    "bot": "Bot",
    "android_app": "Android App",
    "ios_app": "iOS App",
    "game": "Game",
    "game_mod": "Game Mod",
    "browser_extension": "Browser Extension",
    "hardware": "Hardware",
    "other": "Other",
}
# Which rubric row each reason fails (the PDF/CLI still show the 13-check rubric).
CHECK_FOR_REASON = {
    "readme_not_raw": "readme_is_raw_github",
    "no_source": "repo_link_valid",
    "ai_code": "ai_detection",
    "ai_readme": "ai_detection",
    "ai_undeclared": "ai_detection",
    "readme_thin": "readme_substance",
    "no_readme": "readme_substance",
    "demo_broken": "demo_validity",
    "demo_is_repo": "demo_validity",
    "missing_build": "demo_validity",
    "itch_no_build": "demo_validity",
    "bot_link_invalid": "demo_validity",
    "demo_not_testable": "demo_validity",
    "needs_api_key": "demo_credentials",
    "untitled": "description_accuracy",
    "banner_bad": "description_accuracy",
    "banner_default": "description_accuracy",
    "bad_hosting": "demo_link_type",
    "demo_is_video": "demo_link_type",
}
NEAR_MISS_MARGIN = 0.2

JevAsk = Callable[[Mapping[str, Any], Mapping[str, Any]], Awaitable[tuple[dict[str, Any], int]]]


@dataclass(slots=True)
class FirstLayerResult:
    verdict: Literal["REJECT", "PASS"]
    reasons: list[str]
    answers: dict[str, Any]
    facts: dict[str, Any]
    project_type: str
    message: str | None
    video_inputs: RejectVideoInputs
    jev_input_tokens: int = 0
    near_misses: list[str] = field(default_factory=list)
    thresholds: dict[str, float] = field(default_factory=dict)  # Jev limits used

    @property
    def summary(self) -> str:
        if self.verdict == "REJECT":
            labels = ", ".join(REASON_LABELS.get(r, r) for r in self.reasons)
            return f"Rejected automatically: {labels}."
        tail = f" Worth a closer look: {'; '.join(self.near_misses)}." if self.near_misses else ""
        return "Passed the automated checks; needs a human to test the demo." + tail


def jev_asker(settings: Settings) -> JevAsk:
    """One Jev request (all questions in parallel) through OpenRouter."""

    async def ask(state: Mapping[str, Any], questions: Mapping[str, Any]) -> tuple[dict, int]:
        from typesafe_sdk import AsyncTypeSafeClient

        async with AsyncTypeSafeClient(
            api_key=settings.openrouter_api_key,
            base_url=OPENROUTER_TYPESAFE_BASE,
            model=settings.jev_model,
            timeout=settings.jev_timeout,
        ) as client:
            response = await client.system_one(dict(state), dict(questions))
        data = response.model_dump()
        return data["answers"], (data.get("usage") or {}).get("input_tokens") or 0

    return ask


class FirstLayerReviewer:
    def __init__(
        self,
        settings: Settings,
        *,
        ask: JevAsk | None = None,
        banner_agent: Any | None = None,
        thresholds: Mapping[str, float] | None = None,
    ) -> None:
        if not (settings.openrouter_api_key or ask):
            raise RuntimeError("OPENROUTER_API_KEY is required for the first-layer review (Jev)")
        self._settings = settings
        self._ask = ask or jev_asker(settings)
        self._banner_agent = banner_agent
        self._thresholds = dict(thresholds or DEFAULT_THRESHOLDS)

    def _banner(self):
        if self._banner_agent is None:
            self._banner_agent = create_banner_agent(self._settings)
        return self._banner_agent

    async def _evidence(self, prompt: str, cutoff: str) -> dict[str, Any]:
        headers = {"User-Agent": "clanker/0.1", "Accept": "application/vnd.github+json"}
        if self._settings.github_token:
            headers["Authorization"] = f"Bearer {self._settings.github_token}"
        async with (
            httpx.AsyncClient(base_url="https://api.github.com", headers=headers, timeout=20) as gh,
            httpx.AsyncClient(follow_redirects=True, timeout=30) as web,
        ):
            return await gather_evidence(
                prompt, cutoff=cutoff, gh=gh, web=web, vision=self._banner()
            )

    async def review(
        self, packet: ReviewPacket, *, now: datetime | None = None
    ) -> FirstLayerResult:
        prompt = packet.to_prompt()
        cutoff = (now or datetime.now(UTC)).isoformat().replace("+00:00", "Z")
        evidence = await self._evidence(prompt, cutoff)
        state, facts, sections = build_jev_state(prompt, evidence)
        answers, tokens = await self._ask(state, build_reject_questions())
        verdict, reasons = reject_decision(answers, facts, self._thresholds)

        cert = packet.cert
        kind = answers.get("project_type", {}).get("choice") or "other"
        ctx = RejectContext(
            submitter=cert.submitter_username or cert.submitter_name,
            repo_url=cert.repo_url,
            readme_url=cert.readme_url,
            demo_url=cert.demo_url,
            project_type=kind,
            banner_label=facts.get("banner_label"),
            bad_hosts=facts["demo_url_rejected_platforms"],
            ai_style_file=any(
                f["path"].lower().endswith((".css", ".scss")) for f in evidence.get("files") or []
            ),
        )
        video_inputs = RejectVideoInputs(
            ctx=ctx,
            repo_url=cert.repo_url,
            commit=submission_commit(prompt),
            banner_url=packet_field(sections.get("stardance_page", ""), "banner_url") or None,
            readme_markdown=packet.readme or "",
            flagged_code={f["path"]: f["excerpt"] for f in evidence.get("files") or []},
            project_name=cert.project_name,
        )
        near = [
            f"{REASON_LABELS.get(key, key)} {answers[key]['noul']:.2f} (limit {limit:g})"
            for key, limit in self._thresholds.items()
            if key in answers
            and key not in reasons
            and limit - NEAR_MISS_MARGIN <= answers[key]["noul"] < limit
        ]
        css_signals = facts.get("modern_ai_css_signals") or []
        if AI_CSS_REJECT_AT - 2 <= len(css_signals) < AI_CSS_REJECT_AT:
            near.append(
                f"modern AI CSS signals {len(css_signals)} (limit {AI_CSS_REJECT_AT}: "
                f"{', '.join(css_signals)})"
            )
        result = FirstLayerResult(
            verdict=verdict,  # type: ignore[arg-type]
            reasons=reasons,
            answers=answers,
            facts=facts,
            project_type=PROJECT_TYPE_LABELS.get(kind, "Other"),
            message=compose_reject_message(reasons, ctx, cert.id) if verdict == "REJECT" else None,
            video_inputs=video_inputs,
            jev_input_tokens=tokens,
            near_misses=near,
            thresholds=dict(self._thresholds),
        )
        logger.info(
            "First-layer %s for cert %s: %s (jev %d tokens)",
            verdict,
            cert.id,
            reasons or "-",
            tokens,
        )
        return result


def _check(status: CheckStatus, details: str) -> CheckResult:
    return CheckResult(status=status, details=details)


def to_review_output(result: FirstLayerResult) -> ReviewOutput:
    """Express the first-layer result in the existing review shape (Slack, PDF, CLI, chat).

    Checks the first layer doesn't evaluate are marked `skip` ("covered by the human
    reviewer"), never `pass`.
    """
    facts = result.facts
    human = "Not checked automatically; the human reviewer covers this."
    rows: dict[str, CheckResult] = {name: _check(CheckStatus.SKIP, human) for name in (
        "readme_is_raw_github", "readme_matches_repo", "repo_link_valid", "pre_event_commits",
        "ai_detection", "commit_authorship", "readme_boilerplate", "readme_substance",
        "readme_language", "demo_validity", "demo_credentials", "description_accuracy",
        "demo_link_type",
    )}  # fmt: skip
    if facts.get("readme_url_is_raw"):
        rows["readme_is_raw_github"] = _check(CheckStatus.PASS, "README link is the raw file.")
    if facts.get("demo_url_present") and not facts.get("demo_url_rejected_platforms"):
        rows["demo_link_type"] = _check(CheckStatus.PASS, "Demo is not on a disallowed host.")
    for reason in result.reasons:
        check = CHECK_FOR_REASON.get(reason)
        if check:
            previous = rows[check].details if rows[check].status == CheckStatus.FAIL else ""
            detail = REASONS.get(reason, REASON_LABELS.get(reason, reason))
            rows[check] = _check(CheckStatus.FAIL, f"{previous} {detail}".strip())
    css_signals = facts.get("modern_ai_css_signals") or []
    if "ai_code" in result.reasons and len(css_signals) >= AI_CSS_REJECT_AT:
        row = rows["ai_detection"]
        rows["ai_detection"] = _check(
            CheckStatus.FAIL,
            f"{row.details} Modern AI CSS style ({len(css_signals)} signals: "
            f"{', '.join(css_signals)}).",
        )

    flags = ["AI UNDISCLOSED"] if "ai_undeclared" in result.reasons else []
    if result.verdict == "REJECT":
        return ReviewOutput(
            verdict=ReviewVerdict.REJECT,
            project_type=result.project_type,
            checks=ChecksResult(**rows),
            reasoning=result.summary,
            required_fixes=[REASONS.get(r, REASON_LABELS.get(r, r)) for r in result.reasons],
            special_flags=flags or None,
        )
    return ReviewOutput(
        verdict=ReviewVerdict.FLAG_FOR_HUMAN,
        project_type=result.project_type,
        checks=ChecksResult(**rows),
        reasoning=result.summary,
        feedback=[f"Near the limit: {n}" for n in result.near_misses] or None,
        special_flags=flags or None,
    )
