"""Agent-facing review tools: GitHub inspection, URL checks, page fetches.

Ported from v1's ``review_tools.py`` with the messy parts fixed: one shared HTTP
client instead of a client per call, the GitHub token injected from settings
instead of ``os.getenv`` at call time, and no PDF tool (the runner owns report
generation now). Tool names are unchanged so the prompt pack stays accurate.

Every tool returns a JSON string with an ``ok`` flag — errors are data the agent
can reason about, not exceptions.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

GITHUB_API = "https://api.github.com"
TIMEOUT = 20.0
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_URL_FLAGS = {
    "drive.google.com": "google_drive",
    "colab.research.google.com": "colab",
    "huggingface.co": "huggingface",
    ".onrender.com": "render",
    ".up.railway.app": "railway",
    "ngrok": "ngrok",
    "localhost": "localhost",
    "127.0.0.1": "localhost",
}


def _ok(data: Any) -> str:
    payload = {"ok": True, **data} if isinstance(data, dict) else {"ok": True, "data": data}
    return json.dumps(payload)


def _err(reason: str) -> str:
    return json.dumps({"ok": False, "error": reason})


def _parse_github_url(url: str) -> tuple[str, str] | None:
    m = re.match(r"(?:https?://)?github\.com/([^/]+)/([^/\s#?]+)", url.strip())
    if not m:
        return None
    return m.group(1), m.group(2).removesuffix(".git")


def _strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... (truncated, original length: {len(text)} chars)"


def _spa_api_url(url: str) -> str | None:
    """API URL for known SPA sites that return non-200 for valid pages."""
    lower = url.lower().rstrip("/")
    if m := re.match(r"https?://crates\.io/crates/([^/?#]+)", lower):
        return f"https://crates.io/api/v1/crates/{m.group(1)}"
    if m := re.match(r"https?://(?:www\.)?npmjs\.com/package/([^/?#]+)", lower):
        return f"https://registry.npmjs.org/{m.group(1)}"
    if m := re.match(r"https?://pypi\.org/project/([^/?#]+)", lower):
        return f"https://pypi.org/pypi/{m.group(1)}/json"
    return None


class ReviewTools:
    """Bundle of review tools sharing one HTTP connection pool.

    Register on an agent with ``tools=review_tools.all()``.
    """

    def __init__(self, *, github_token: str = "") -> None:
        github_headers = {"Accept": "application/vnd.github+json", "User-Agent": "clanker/0.1"}
        if github_token:
            github_headers["Authorization"] = f"Bearer {github_token}"
        self._github = httpx.AsyncClient(
            base_url=GITHUB_API, timeout=TIMEOUT, headers=github_headers
        )
        self._web = httpx.AsyncClient(
            timeout=TIMEOUT, follow_redirects=True, headers=BROWSER_HEADERS
        )

    async def aclose(self) -> None:
        await self._github.aclose()
        await self._web.aclose()

    def all(self) -> list:
        """All tool functions, for registering on a pydantic-ai Agent."""
        return [
            self.review_get_github_repo_info,
            self.review_get_github_readme,
            self.review_get_github_commits,
            self.review_get_github_languages,
            self.review_get_github_repo_tree,
            self.review_get_github_file_content,
            self.review_get_github_releases,
            self.review_search_github_code,
            self.review_check_url,
            self.review_fetch_page_text,
            self.review_fetch_stardance_project,
        ]

    # ---------------------------------------------------------------- github

    async def review_get_github_repo_info(self, repo_url: str) -> str:
        """Check if a GitHub repository exists and is public.

        Returns visibility, default branch, language, description, and star/fork
        counts. Use this FIRST to verify the repo is accessible.
        """
        parsed = _parse_github_url(repo_url)
        if not parsed:
            return _err(f"Could not parse GitHub URL: {repo_url}")
        owner, repo = parsed
        try:
            r = await self._github.get(f"/repos/{owner}/{repo}")
            if r.status_code == 404:
                return _err("Repository not found (404) — may not exist or is private")
            if r.status_code != 200:
                return _err(f"GitHub API returned status {r.status_code}")
            data = r.json()
            return _ok(
                {
                    "owner": owner,
                    "repo": repo,
                    "exists": True,
                    "private": data.get("private", False),
                    "default_branch": data.get("default_branch", "main"),
                    "language": data.get("language"),
                    "description": data.get("description"),
                    "stars": data.get("stargazers_count", 0),
                    "forks": data.get("forks_count", 0),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "topics": data.get("topics", []),
                }
            )
        except Exception as e:
            return _err(f"Failed to check repo: {e}")

    async def review_get_github_readme(self, repo_url: str) -> str:
        """Fetch the README of a GitHub repository straight from GitHub.

        The packet already contains the dashboard's cached README — use this to
        cross-check it or when the packet copy is missing/empty.
        """
        parsed = _parse_github_url(repo_url)
        if not parsed:
            return _err(f"Could not parse GitHub URL: {repo_url}")
        owner, repo = parsed
        try:
            r = await self._github.get(
                f"/repos/{owner}/{repo}/readme",
                headers={"Accept": "application/vnd.github.raw+json"},
            )
            if r.status_code == 404:
                return json.dumps({"ok": True, "exists": False, "content": None})
            if r.status_code != 200:
                return _err(f"GitHub API returned status {r.status_code}")
            return json.dumps(
                {
                    "ok": True,
                    "exists": True,
                    "content": _truncate(r.text, 30000),
                    "length": len(r.text),
                }
            )
        except Exception as e:
            return _err(f"Failed to fetch README: {e}")

    async def review_get_github_commits(self, repo_url: str, per_page: int = 30) -> str:
        """Fetch recent commits: authors, dates, messages.

        Use for pre-event activity (commits before Dec 25, 2024), authorship,
        and suspicious patterns (single huge commit, no commits).
        """
        parsed = _parse_github_url(repo_url)
        if not parsed:
            return _err(f"Could not parse GitHub URL: {repo_url}")
        owner, repo = parsed
        per_page = max(1, min(per_page, 100))
        try:
            r = await self._github.get(
                f"/repos/{owner}/{repo}/commits", params={"per_page": per_page}
            )
            if r.status_code != 200:
                return _err(f"GitHub API returned status {r.status_code}")
            commits = []
            for c in r.json():
                commit = c.get("commit", {})
                author = commit.get("author", {})
                committer = commit.get("committer", {})
                commits.append(
                    {
                        "sha": c.get("sha", "")[:7],
                        "message": commit.get("message", "")[:200],
                        "author_name": author.get("name"),
                        "author_email": author.get("email"),
                        "author_date": author.get("date"),
                        "committer_name": committer.get("name"),
                        "committer_date": committer.get("date"),
                        "github_author": (c.get("author") or {}).get("login"),
                    }
                )
            return _ok({"total_fetched": len(commits), "commits": commits})
        except Exception as e:
            return _err(f"Failed to fetch commits: {e}")

    async def review_get_github_languages(self, repo_url: str) -> str:
        """Language -> bytes breakdown; helps detect the actual project type."""
        parsed = _parse_github_url(repo_url)
        if not parsed:
            return _err(f"Could not parse GitHub URL: {repo_url}")
        owner, repo = parsed
        try:
            r = await self._github.get(f"/repos/{owner}/{repo}/languages")
            if r.status_code != 200:
                return _err(f"GitHub API returned status {r.status_code}")
            return _ok({"languages": r.json()})
        except Exception as e:
            return _err(f"Failed to fetch languages: {e}")

    async def review_get_github_repo_tree(self, repo_url: str) -> str:
        """Full file listing of the repo.

        Use to detect project type via marker files (package.json, Cargo.toml,
        …) and to spot committed secrets (.env files etc.).
        """
        parsed = _parse_github_url(repo_url)
        if not parsed:
            return _err(f"Could not parse GitHub URL: {repo_url}")
        owner, repo = parsed
        try:
            r = await self._github.get(
                f"/repos/{owner}/{repo}/git/trees/HEAD", params={"recursive": "1"}
            )
            if r.status_code != 200:
                return _err(f"GitHub API returned status {r.status_code}")
            tree = r.json().get("tree", [])
            files = [item["path"] for item in tree if item.get("type") in ("blob", "tree")]
            truncated = len(files) > 500
            return _ok({"file_count": len(tree), "files": files[:500], "truncated": truncated})
        except Exception as e:
            return _err(f"Failed to fetch repo tree: {e}")

    async def review_get_github_file_content(self, repo_url: str, file_path: str) -> str:
        """Read one file from the repo (hardcoded keys, configs, code claims)."""
        parsed = _parse_github_url(repo_url)
        if not parsed:
            return _err(f"Could not parse GitHub URL: {repo_url}")
        owner, repo = parsed
        try:
            r = await self._github.get(
                f"/repos/{owner}/{repo}/contents/{file_path}",
                headers={"Accept": "application/vnd.github.raw+json"},
            )
            if r.status_code == 404:
                return _err(f"File not found: {file_path}")
            if r.status_code != 200:
                return _err(f"GitHub API returned status {r.status_code}")
            return json.dumps(
                {
                    "ok": True,
                    "path": file_path,
                    "content": _truncate(r.text, 50000),
                    "length": len(r.text),
                }
            )
        except Exception as e:
            return _err(f"Failed to fetch file: {e}")

    async def review_get_github_releases(self, repo_url: str) -> str:
        """List GitHub Releases and their assets.

        Use for CLI tools and desktop apps: do releases contain actual compiled
        binaries, or only auto-generated source archives?
        """
        parsed = _parse_github_url(repo_url)
        if not parsed:
            return _err(f"Could not parse GitHub URL: {repo_url}")
        owner, repo = parsed
        try:
            r = await self._github.get(
                f"/repos/{owner}/{repo}/releases", params={"per_page": 10}
            )
            if r.status_code != 200:
                return _err(f"GitHub API returned status {r.status_code}")
            releases = []
            for rel in r.json():
                assets = [
                    {
                        "name": a.get("name"),
                        "size_bytes": a.get("size"),
                        "content_type": a.get("content_type"),
                        "download_count": a.get("download_count"),
                    }
                    for a in rel.get("assets", [])
                ]
                releases.append(
                    {
                        "tag": rel.get("tag_name"),
                        "name": rel.get("name"),
                        "prerelease": rel.get("prerelease", False),
                        "draft": rel.get("draft", False),
                        "created_at": rel.get("created_at"),
                        "asset_count": len(assets),
                        "assets": assets,
                        "has_source_only": not assets,
                    }
                )
            return _ok({"total_fetched": len(releases), "releases": releases})
        except Exception as e:
            return _err(f"Failed to fetch releases: {e}")

    async def review_search_github_code(self, repo_url: str, query: str) -> str:
        """Search repo code for patterns (API keys, secrets).

        Rate-limited by GitHub; prefer review_get_github_repo_tree +
        review_get_github_file_content for targeted inspection.
        """
        parsed = _parse_github_url(repo_url)
        if not parsed:
            return _err(f"Could not parse GitHub URL: {repo_url}")
        owner, repo = parsed
        try:
            r = await self._github.get(
                "/search/code", params={"q": f"{query} repo:{owner}/{repo}"}
            )
            if r.status_code in (401, 403):
                return _err(
                    f"GitHub search API returned {r.status_code} (auth required or rate "
                    "limited). Use review_get_github_repo_tree + "
                    "review_get_github_file_content instead."
                )
            if r.status_code != 200:
                return _err(f"GitHub search API returned status {r.status_code}")
            data = r.json()
            matches = [
                {"path": i.get("path"), "name": i.get("name"), "url": i.get("html_url")}
                for i in data.get("items", [])[:20]
            ]
            return _ok({"total_count": data.get("total_count", 0), "matches": matches})
        except Exception as e:
            return _err(f"Code search failed: {e}")

    # ------------------------------------------------------------------- web

    async def review_check_url(self, url: str) -> str:
        """Check if a URL is reachable: status code, final URL, content type.

        Also flags problematic platforms (google_drive, colab, huggingface,
        render, railway, ngrok, localhost). Does NOT return page content — use
        review_fetch_page_text for that.
        """
        if not url or not url.startswith(("http://", "https://")):
            return _err(f"Invalid URL: {url}")
        lower = url.lower()
        flags = [flag for marker, flag in _URL_FLAGS.items() if marker in lower]
        flags = list(dict.fromkeys(flags))
        try:
            r = await self._web.get(url)
            reachable = 200 <= r.status_code < 400
            # SPA fallback: crates.io/npm/PyPI pages can return non-200 for valid
            # resources; confirm via their APIs.
            if not reachable and (api_url := _spa_api_url(url)):
                try:
                    api_r = await self._web.get(api_url)
                    if 200 <= api_r.status_code < 400:
                        reachable = True
                        flags.append("spa_verified_via_api")
                except Exception:
                    pass
            return _ok(
                {
                    "url": url,
                    "final_url": str(r.url),
                    "status_code": r.status_code,
                    "reachable": reachable,
                    "content_type": r.headers.get("content-type", ""),
                    "flags": flags or None,
                }
            )
        except Exception as e:
            return json.dumps(
                {
                    "ok": True,
                    "url": url,
                    "reachable": False,
                    "error": str(e),
                    "flags": flags or None,
                }
            )

    async def review_fetch_page_text(self, url: str) -> str:
        """Fetch a page and return its visible text (HTML stripped, 20k chars max).

        Use to read demo pages, check for AI-generated site content, or verify a
        deployed app shows real content.
        """
        if not url or not url.startswith(("http://", "https://")):
            return _err(f"Invalid URL: {url}")
        try:
            r = await self._web.get(url)
            if r.status_code >= 400:
                return _err(f"HTTP {r.status_code} fetching {url}")
            content_type = r.headers.get("content-type", "")
            text = _strip_html(r.text) if "text/html" in content_type else r.text
            return json.dumps(
                {
                    "ok": True,
                    "url": url,
                    "text": _truncate(text, 20000),
                    "content_type": content_type,
                }
            )
        except Exception as e:
            return _err(f"Failed to fetch page: {e}")

    async def review_fetch_stardance_project(self, project_url: str) -> str:
        """Fetch a Stardance project page's text (AI disclosure, update flag).

        Fallback only — the packet's ai_declaration/updated_project fields are
        authoritative when present.
        """
        if not project_url or "stardance.hackclub.com" not in project_url:
            return _err(f"Not a Stardance URL: {project_url}")
        try:
            r = await self._web.get(project_url)
            if r.status_code >= 400:
                return _err(f"HTTP {r.status_code} fetching Stardance project")
            return json.dumps(
                {"ok": True, "url": project_url, "text": _truncate(_strip_html(r.text), 20000)}
            )
        except Exception as e:
            return _err(f"Failed to fetch Stardance project: {e}")
