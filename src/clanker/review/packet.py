"""Build the submission packet the review agent starts from.

Pre-fetches everything the dashboard already has (detail + cached GitHub data +
cached README + prior reviews) plus the deterministic lookups the agent used to
burn tool rounds on every run (repo tree, languages, Stardance ship page), so
the agent spends its tool calls on actual investigation instead of
re-downloading basics.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any

from clanker.review.tools import ReviewTools
from clanker.shipwrights import (
    CertDetail,
    FeedbackTemplates,
    GitHubData,
    NotFoundError,
    ReadmeData,
    ShipwrightsClient,
)

README_LIMIT = 30000
STARDANCE_TEXT_LIMIT = 12000
# The cert's external_id is the Stardance *ship* id, not a public project id.
# The project is reachable only through the admin ship page (login required) —
# /projects/{external_id} points at an unrelated project, so never build that.
STARDANCE_SHIP_BASE = "https://stardance.hackclub.com/admin/certification/ship"


@dataclass(slots=True)
class ReviewPacket:
    cert: CertDetail
    github: GitHubData | None
    readme: str
    readme_data: ReadmeData | None = None
    feedback_templates: FeedbackTemplates | None = None
    # Parsed tool payloads (``ok`` dicts), pre-fetched so the agent doesn't
    # spend a model round asking for them. None when unavailable/failed.
    tree: dict[str, Any] | None = None
    languages: dict[str, Any] | None = None
    stardance: dict[str, Any] | None = None
    demo_render: dict[str, Any] | None = None

    @property
    def private_context(self) -> list[str]:
        """Reviewer-only strings that must never be copied into public output."""
        note = (self.cert.internal_notes or "").strip()
        return [note] if note else []

    @property
    def stardance_url(self) -> str | None:
        """Stardance admin ship page for this cert (requires a Stardance login)."""
        if self.cert.external_id:
            return f"{STARDANCE_SHIP_BASE}/{self.cert.external_id}?via=dashboard"
        return None

    def to_prompt(self) -> str:
        """Render the packet as the user message for the review agent."""
        c = self.cert
        lines = [
            f"Review this submission (cert id: {c.id}).",
            "",
            "## Submission",
            f"- Project name: {c.project_name}",
            f"- Stardance ship page (needs login): {self.stardance_url or '(unknown ship id)'}",
            f"- Claimed project type: {c.project_type or 'n/a'} "
            f"(AI-detected: {c.ai_type or 'n/a'})",
            f"- Ship type: {c.ship_type or 'n/a'}",
            f"- Dashboard status: {c.status.value}",
            f"- Submitter: {c.submitter_username or c.submitter_slack_id or 'unknown'}",
            f"- Description: {c.description or '(none)'}",
            f"- AI declaration: {c.ai_declaration or '(none)'}",
            f"- Updated project: {c.updated_project or '(not declared as update)'}",
            f"- Demo URL: {c.demo_url or '(none)'}",
            f"- Repo URL: {c.repo_url or '(none)'}",
            f"- Readme URL: {c.readme_url or '(none)'}",
            f"- Dev time: {c.dev_time or 'n/a'}",
            f"- Hackatime projects: {', '.join(c.hackatime_projects) or 'n/a'}",
            f"- Proof video: {c.proof_video_url or '(not uploaded)'}",
            f"- Proof video required: {c.proof_video_required}",
            f"- Feedback required: {c.feedback_required}",
            f"- Dashboard AI indexing: {c.ai_index_state or 'n/a'}"
            + (f" (error: {c.ai_index_error})" if c.ai_index_error else ""),
        ]

        if c.claimer or c.claimed_at:
            claimer = None
            if c.claimer:
                claimer = c.claimer.display_name or c.claimer.slack_username or c.claimer.id
            lines.append(
                f"- Claimed by: {claimer or c.claimer_id or '?'} at "
                f"{c.claimed_at.isoformat() if c.claimed_at else '?'}"
            )
        if c.return_reason:
            lines.append(f"- Current return reason: {c.return_reason}")

        if c.internal_notes:
            lines += [
                "",
                "## PRIVATE reviewer context",
                "The following internal note may guide investigation, but it is not public "
                "evidence. Never quote, paraphrase, mention, or expose it in reasoning, "
                "checks, fixes, feedback, flags, PDFs, videos, or Slack output.",
                "",
                c.internal_notes,
            ]

        if c.attempts:
            lines += ["", "## Submission attempts and review history (oldest first)"]
            for attempt in sorted(
                c.attempts,
                key=lambda a: a.created_at.isoformat() if a.created_at else "",
            ):
                when = attempt.created_at.date().isoformat() if attempt.created_at else "?"
                current = " · current attempt" if attempt.id == c.id else ""
                lines.append(
                    f"- Attempt {attempt.id} · {when} · {attempt.status.value}{current}"
                )
                if attempt.return_reason:
                    lines.append(f"  - Return reason: {attempt.return_reason}")
                for review in sorted(attempt.reviews, key=lambda r: r.created_at):
                    reviewer = None
                    if review.reviewer:
                        reviewer = review.reviewer.display_name or review.reviewer.slack_username
                    who = f" by {reviewer}" if reviewer else ""
                    lines.append(
                        f"  - {review.created_at.date().isoformat()} {review.verdict.value}{who}: "
                        f"{review.comment or '(no comment)'}"
                    )
        elif c.reviews:
            # Compatibility with older Dashboard responses that had no attempts.
            lines += ["", "## Prior reviews (newest first)"]
            for review in sorted(c.reviews, key=lambda r: r.created_at, reverse=True):
                when = review.created_at.date().isoformat()
                lines.append(f"- {when} {review.verdict.value}: {review.comment or '(no comment)'}")

        if c.active_events:
            lines += ["", "## Active Dashboard events", json.dumps(c.active_events)]

        if self.github and (self.github.repo or self.github.commits):
            lines += ["", "## GitHub (cached by dashboard)"]
            cache_bits = [
                f"status {self.github.status or '?'}",
                f"cached {self.github.cached}",
                f"fetched {self.github.fetched_at.isoformat() if self.github.fetched_at else '?'}",
            ]
            lines.append("- Cache metadata: " + " · ".join(cache_bits))
            if self.github.repo:
                repo = self.github.repo
                lines.append(
                    f"- Repo: {repo.full_name or '?'} · language {repo.language or '?'} · "
                    f"created {repo.created_at.date().isoformat() if repo.created_at else '?'}"
                )
            for commit in self.github.commits[:30]:
                when = commit.date.isoformat() if commit.date else "?"
                author = commit.author_login or commit.author_name or "?"
                message = (commit.message or "").splitlines()[0][:100]
                lines.append(f"- {commit.short_sha or '?'} {when} {author}: {message}")

        if self.languages or self.tree:
            lines += ["", "## Repo structure (pre-fetched — do not re-fetch)"]
            if self.languages:
                langs = self.languages.get("languages") or {}
                breakdown = ", ".join(f"{name} ({size} bytes)" for name, size in langs.items())
                lines.append(f"- Languages: {breakdown or '(none reported)'}")
            if self.tree:
                files = self.tree.get("files") or []
                count = self.tree.get("file_count", len(files))
                suffix = " (listing truncated)" if self.tree.get("truncated") else ""
                lines.append(f"- File tree ({count} entries{suffix}):")
                lines += [f"  - {path}" for path in files]

        if self.stardance:
            lines += ["", "## Stardance ship page (pre-fetched — do not re-fetch)"]
            if self.stardance.get("ok"):
                for key, value in (self.stardance.get("summary") or {}).items():
                    lines.append(f"- {key}: {value}")
                devlogs = self.stardance.get("devlogs") or []
                if devlogs:
                    lines += ["", "### Deduplicated devlogs"]
                    for devlog in devlogs:
                        body = (devlog.get("text") or "")[:700]
                        lines.append(
                            f"- {devlog.get('created_at') or '?'} · devlog "
                            f"{devlog.get('id') or '?'} · media "
                            f"{devlog.get('media_count', len(devlog.get('media') or []))}: "
                            f"{body or '(no text)'}"
                        )
                completeness = self.stardance.get("completeness") or {}
                if completeness:
                    lines.append(
                        "- Devlog completeness: "
                        f"returned {completeness.get('returned_devlogs', 0)} of "
                        f"{completeness.get('total_devlogs', 0)}"
                    )
                text = self.stardance.get("fallback_text") or ""
                if text and not devlogs:
                    lines += ["", "```", text[:STARDANCE_TEXT_LIMIT], "```"]
            else:
                # Surface the failure verbatim — a redirected-away ship page is
                # itself a review signal (removed project / expired login).
                lines.append(f"- fetch failed: {self.stardance.get('error') or 'unknown error'}")

        if self.demo_render:
            r = self.demo_render
            final = r.get("final_url") or "?"
            lines += [
                "",
                "## Demo page render (pre-fetched, JavaScript executed — do not re-render)",
                f"- Final URL: {final} (HTTP {r.get('status_code') or '?'})",
            ]
            if r.get("viewport_mostly_empty"):
                lines.append(
                    "- Viewport was mostly empty after load (almost no visible text rendered)"
                )
            if description := r.get("screenshot_description"):
                lines += [
                    "",
                    "What a vision model sees in the screenshot "
                    "(description only — judge it yourself):",
                    "",
                    description,
                ]
            if text := r.get("rendered_text"):
                lines += ["", "Rendered visible text:", "", "```", text, "```"]

        lines += ["", "## README (cached by dashboard)"]
        if self.readme_data:
            fetched_at = (
                self.readme_data.fetched_at.isoformat()
                if self.readme_data.fetched_at
                else "?"
            )
            lines.append(
                f"Cache status: {self.readme_data.status or '?'} · "
                f"cached {self.readme_data.cached} · "
                f"fetched {fetched_at}"
            )
        if self.readme:
            readme = self.readme
            if len(readme) > README_LIMIT:
                original = len(self.readme)
                readme = readme[:README_LIMIT] + f"\n\n... (truncated from {original} chars)"
            lines += ["", "```markdown", readme, "```"]
        else:
            lines.append("(README missing or empty — verify with get_github_readme)")

        if self.feedback_templates:
            templates = self.feedback_templates.shared + self.feedback_templates.mine
            if templates:
                lines += [
                    "",
                    "## Reviewer feedback templates (wording reference only; not evidence)",
                ]
                for template in templates[:10]:
                    body = template.body[:1000]
                    lines.append(f"- {template.title}: {body}")

        return "\n".join(lines)


async def _tool_payload(call: Awaitable[str]) -> dict[str, Any] | None:
    """Run a ReviewTools coroutine and parse its JSON payload; None on failure."""
    try:
        data = json.loads(await call)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


async def build_packet(
    client: ShipwrightsClient, cert_id: str, tools: ReviewTools | None = None
) -> ReviewPacket:
    cert = await client.get_certification(cert_id)

    async def get_github() -> GitHubData | None:
        try:
            return await client.get_github(cert_id)
        except NotFoundError:
            return None
        except Exception:
            # GitHub cache failures shouldn't kill the review — the agent has tools.
            return None

    async def get_readme() -> ReadmeData | None:
        try:
            return await client.get_readme_data(cert_id)
        except Exception:
            return None

    async def get_feedback_templates() -> FeedbackTemplates | None:
        if not cert.feedback_templates_enabled:
            return None
        try:
            return await client.get_feedback_templates()
        except Exception:
            return None

    async def get_tree() -> dict[str, Any] | None:
        if not (tools and cert.repo_url):
            return None
        payload = await _tool_payload(tools.get_github_repo_tree(cert.repo_url))
        return payload if payload and payload.get("ok") else None

    async def get_languages() -> dict[str, Any] | None:
        if not (tools and cert.repo_url):
            return None
        payload = await _tool_payload(tools.get_github_languages(cert.repo_url))
        return payload if payload and payload.get("ok") else None

    async def get_demo_render() -> dict[str, Any] | None:
        if not (tools and cert.demo_url):
            return None
        # A failed render (no browser, timeout) isn't evidence either way — the
        # agent still has render/fetch tools; only ship useful payloads.
        payload = await _tool_payload(tools.render_page(cert.demo_url))
        return payload if payload and payload.get("ok") else None

    async def get_stardance() -> dict[str, Any] | None:
        if not (tools and cert.external_id):
            return None
        url = f"{STARDANCE_SHIP_BASE}/{cert.external_id}?via=dashboard"
        # Keep non-ok payloads: redirected_away is a review signal, not a fetch bug.
        return await _tool_payload(tools.fetch_stardance_project(url))

    github, readme_data, feedback_templates, tree, languages, stardance, demo_render = (
        await asyncio.gather(
            get_github(),
            get_readme(),
            get_feedback_templates(),
            get_tree(),
            get_languages(),
            get_stardance(),
            get_demo_render(),
        )
    )

    return ReviewPacket(
        cert=cert,
        github=github,
        readme=readme_data.markdown if readme_data else "",
        readme_data=readme_data,
        feedback_templates=feedback_templates,
        tree=tree,
        languages=languages,
        stardance=stardance,
        demo_render=demo_render,
    )
