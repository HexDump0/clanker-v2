"""Code-hosting forges other than GitHub: GitLab, Gitea/Forgejo (Codeberg), Bitbucket, sourcehut.

The Shipwrights Dashboard only caches GitHub repos (README status ``not_github`` otherwise),
so for everything else clanker builds the URLs itself. Every forge here accepts ``HEAD`` as
a ref in raw/blob URLs (verified live 2026-10-01).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

import httpx

ForgeKind = Literal["github", "gitlab", "gitea", "bitbucket", "sourcehut"]

# Hosts recognised by name; self-hosted instances are matched by a conventional prefix.
_HOSTS: dict[str, ForgeKind] = {
    "github.com": "github",
    "gitlab.com": "gitlab",
    "codeberg.org": "gitea",
    "gitea.com": "gitea",
    "bitbucket.org": "bitbucket",
    "git.sr.ht": "sourcehut",
}
_PREFIXES: tuple[tuple[str, ForgeKind], ...] = (
    ("gitlab.", "gitlab"),
    ("gitea.", "gitea"),
    ("forgejo.", "gitea"),
)
README_NAMES = ("README.md", "readme.md", "Readme.md", "README.MD", "README", "README.rst",
                "README.txt")  # fmt: skip
README_LIMIT_BYTES = 200_000


def _kind_for(host: str) -> ForgeKind | None:
    host = host.lower().removeprefix("www.")
    return _HOSTS.get(host) or next((k for p, k in _PREFIXES if host.startswith(p)), None)


@dataclass(frozen=True, slots=True)
class Repo:
    kind: ForgeKind
    host: str
    path: str  # "owner/name"; GitLab may nest groups; sourcehut is "~user/name"

    @property
    def web_url(self) -> str:
        return f"https://{self.host}/{self.path}"

    @property
    def releases_url(self) -> str:
        return {
            "github": f"{self.web_url}/releases",
            "gitlab": f"{self.web_url}/-/releases",
            "gitea": f"{self.web_url}/releases",
            "bitbucket": f"{self.web_url}/downloads/",
            "sourcehut": f"{self.web_url}/refs",
        }[self.kind]

    def blob_url(self, ref: str, path: str) -> str:
        """The human-readable file page."""
        return {
            "github": f"{self.web_url}/blob/{ref}/{path}",
            "gitlab": f"{self.web_url}/-/blob/{ref}/{path}",
            "gitea": f"{self.web_url}/src/{ref}/{path}",
            "bitbucket": f"{self.web_url}/src/{ref}/{path}",
            "sourcehut": f"{self.web_url}/tree/{ref}/item/{path}",
        }[self.kind]

    def raw_url(self, ref: str, path: str) -> str:
        """The plain file (what Stardance needs for the README link)."""
        if self.kind == "github":
            return f"https://raw.githubusercontent.com/{self.path}/{ref}/{path}"
        return {
            "gitlab": f"{self.web_url}/-/raw/{ref}/{path}",
            "gitea": f"{self.web_url}/raw/{ref}/{path}",
            "bitbucket": f"{self.web_url}/raw/{ref}/{path}",
            "sourcehut": f"{self.web_url}/blob/{ref}/{path}",
        }[self.kind]


def parse_repo(url: str | None) -> Repo | None:
    """The repo a URL points into (repo root or any page inside it), or None."""
    m = re.match(r"https?://([^/\s?#]+)/([^\s?#]+)", (url or "").strip())
    if not m:
        return None
    host = m.group(1).lower().removeprefix("www.")
    if host == "raw.githubusercontent.com":
        host = "github.com"
    kind = _kind_for(host)
    if kind is None:
        return None
    parts = [p for p in m.group(2).split("/") if p]
    if kind == "gitlab":
        # Groups can nest: everything before the "/-/" route separator is the project path.
        parts = parts[: parts.index("-")] if "-" in parts else parts
        if len(parts) < 2:
            return None
    else:
        parts = parts[:2]
        if len(parts) < 2 or (kind == "sourcehut" and not parts[0].startswith("~")):
            return None
    parts[-1] = parts[-1].removesuffix(".git")
    return Repo(kind=kind, host=host, path="/".join(parts))


def is_raw_file_url(url: str | None) -> bool:
    """A link that serves the file itself rather than a forge page around it."""
    url = (url or "").strip()
    if url.startswith("https://raw.githubusercontent.com/"):
        return True
    repo = parse_repo(url)
    if repo is None or repo.kind == "github":
        return False
    rest = url.split(repo.path, 1)[-1]
    return {
        "gitlab": rest.startswith("/-/raw/"),
        "gitea": rest.startswith("/raw/"),
        "bitbucket": rest.startswith("/raw/"),
        "sourcehut": rest.startswith("/blob/"),
    }[repo.kind]


def raw_readme_url(readme_url: str | None, repo_url: str | None) -> str | None:
    """Best-effort raw link for the README: convert a blob link, else the default branch."""
    if is_raw_file_url(readme_url):
        return (readme_url or "").strip()
    repo = parse_repo(readme_url) or parse_repo(repo_url)
    if repo is None:
        return None
    rest = (readme_url or "").split(repo.path, 1)[-1] if parse_repo(readme_url) else ""
    pattern = {
        "github": r"^/blob/([^/]+)/(.+?)/?$",
        "gitlab": r"^/-/blob/([^/]+)/(.+?)/?$",
        "gitea": r"^/src/(?:branch/|commit/|tag/)?([^/]+)/(.+?)/?$",
        "bitbucket": r"^/src/([^/]+)/(.+?)/?$",
        "sourcehut": r"^/tree/([^/]+)/item/(.+?)/?$",
    }[repo.kind]
    m = re.match(pattern, rest)
    if m:
        ref, path = m.groups()
        if repo.kind == "github":  # keep the GitHub form reviewers already use
            return f"https://raw.githubusercontent.com/{repo.path}/refs/heads/{ref}/{path}"
        return repo.raw_url(ref, path)
    return repo.raw_url("HEAD", "README.md") if repo.kind != "github" else None


async def fetch_readme(
    repo_url: str | None, readme_url: str | None, web: httpx.AsyncClient
) -> tuple[str, str] | None:
    """(markdown, source URL) fetched straight from the forge, or None when not found.

    Raises ``httpx.HTTPError`` on network failure so callers can tell "missing" from
    "couldn't check".
    """
    repo = parse_repo(repo_url) or parse_repo(readme_url)
    candidates: list[str] = []
    if is_raw_file_url(readme_url):
        candidates.append((readme_url or "").strip())
    elif raw := raw_readme_url(readme_url, repo_url):
        candidates.append(raw)
    if repo is not None:
        candidates += [repo.raw_url("HEAD", quote(name)) for name in README_NAMES]
    for url in dict.fromkeys(candidates):
        r = await web.get(url, follow_redirects=True)
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and not ctype.startswith("text/html") and r.text.strip():
            return r.text[:README_LIMIT_BYTES], url
    return None
