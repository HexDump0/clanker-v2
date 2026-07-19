"""Build the submission packet the review agent starts from.

Pre-fetches everything the dashboard already has (detail + cached GitHub data +
cached README + prior reviews) so the agent spends its tool calls on actual
investigation instead of re-downloading basics.
"""

from __future__ import annotations

from dataclasses import dataclass

from clanker.shipwrights import CertDetail, GitHubData, NotFoundError, ShipwrightsClient

README_LIMIT = 30000


@dataclass(slots=True)
class ReviewPacket:
    cert: CertDetail
    github: GitHubData | None
    readme: str

    def to_prompt(self) -> str:
        """Render the packet as the user message for the review agent."""
        c = self.cert
        lines = [
            f"Review this submission (cert id: {c.id}).",
            "",
            "## Submission",
            f"- Project name: {c.project_name}",
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

        lines += ["", "## README (cached by dashboard)"]
        if self.readme:
            readme = self.readme
            if len(readme) > README_LIMIT:
                original = len(self.readme)
                readme = readme[:README_LIMIT] + f"\n\n... (truncated from {original} chars)"
            lines += ["", "```markdown", readme, "```"]
        else:
            lines.append("(README missing or empty — verify with review_get_github_readme)")

        return "\n".join(lines)


async def build_packet(client: ShipwrightsClient, cert_id: str) -> ReviewPacket:
    cert = await client.get_certification(cert_id)

    github: GitHubData | None = None
    try:
        github = await client.get_github(cert_id)
    except NotFoundError:
        pass
    except Exception:
        # GitHub cache failures shouldn't kill the review — the agent has tools.
        github = None

    try:
        readme = await client.get_readme(cert_id)
    except Exception:
        readme = ""

    return ReviewPacket(cert=cert, github=github, readme=readme)
