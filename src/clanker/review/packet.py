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
from clanker.shipwrights import CertDetail, GitHubData, NotFoundError, ShipwrightsClient

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
    # Parsed tool payloads (``ok`` dicts), pre-fetched so the agent doesn't
    # spend a model round asking for them. None when unavailable/failed.
    tree: dict[str, Any] | None = None
    languages: dict[str, Any] | None = None
    stardance: dict[str, Any] | None = None
    demo_render: dict[str, Any] | None = None

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
            f"- Submitter: {c.submitter_username or c.submitter_slack_id or 'unknown'}",
            f"- Description: {c.description or '(none)'}",
            f"- AI declaration: {c.ai_declaration or '(none)'}",
            f"- Updated project: {c.updated_project or '(not declared as update)'}",
            f"- Demo URL: {c.demo_url or '(none)'}",
            f"- Repo URL: {c.repo_url or '(none)'}",
            f"- Readme URL: {c.readme_url or '(none)'}",
            f"- Dev time: {c.dev_time or 'n/a'}",
            f"- Hackatime projects: {', '.join(c.hackatime_projects) or 'n/a'}",
        ]

        if c.reviews:
            lines += ["", "## Prior reviews (newest first)"]
            for review in sorted(c.reviews, key=lambda r: r.created_at, reverse=True):
                when = review.created_at.date().isoformat()
                lines.append(f"- {when} {review.verdict.value}: {review.comment or '(no comment)'}")

        if self.github and (self.github.repo or self.github.commits):
            lines += ["", "## GitHub (cached by dashboard)"]
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
                for key, value in (self.stardance.get("meta") or {}).items():
                    lines.append(f"- {key}: {value}")
                text = self.stardance.get("text") or ""
                if len(text) > STARDANCE_TEXT_LIMIT:
                    text = text[:STARDANCE_TEXT_LIMIT] + " ... (truncated)"
                if text:
                    lines += ["", "```", text, "```"]
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
        if self.readme:
            readme = self.readme
            if len(readme) > README_LIMIT:
                original = len(self.readme)
                readme = readme[:README_LIMIT] + f"\n\n... (truncated from {original} chars)"
            lines += ["", "```markdown", readme, "```"]
        else:
            lines.append("(README missing or empty — verify with get_github_readme)")

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

    async def get_readme() -> str:
        try:
            return await client.get_readme(cert_id)
        except Exception:
            return ""

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

    github, readme, tree, languages, stardance, demo_render = await asyncio.gather(
        get_github(), get_readme(), get_tree(), get_languages(), get_stardance(),
        get_demo_render(),
    )

    return ReviewPacket(
        cert=cert,
        github=github,
        readme=readme,
        tree=tree,
        languages=languages,
        stardance=stardance,
        demo_render=demo_render,
    )
