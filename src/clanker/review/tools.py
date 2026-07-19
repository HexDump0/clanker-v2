"""Agent-facing review tools: GitHub inspection, URL checks, page fetches.

Ported from v1's ``review_tools.py`` with the messy parts fixed: one shared HTTP
client instead of a client per call, the GitHub token injected from settings
instead of ``os.getenv`` at call time, and no PDF tool (the runner owns report
generation now). Tool names are unchanged so the prompt pack stays accurate.

Every tool returns a JSON string with an ``ok`` flag — errors are data the agent
can reason about, not exceptions.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

GITHUB_API = "https://api.github.com"
STARDANCE_COOKIE_NAME = "_stardance_session_v3"
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


# Matches a full HTML tag even when an attribute value contains a bare ">"
# (Stardance's Stimulus actions like `turbo:submit-end->modal#close"` broke the
# naive `<[^>]+>` strip, leaking attribute fragments into the text).
_TAG_RE = re.compile(r"""<(?:[^>"']|"[^"]*"|'[^']*')*>""")
_DROP_ELEMENTS_RE = re.compile(
    r"<(script|style|noscript|svg|template|head)\b[^>]*>.*?</\1>", re.S | re.I
)


def _strip_html(markup: str) -> str:
    text = _DROP_ELEMENTS_RE.sub(" ", markup)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


# name/property -> normalised key we surface to the agent. First match wins, so
# the richer `og:`/`twitter:` variants take precedence over bare `name=`.
_META_FIELDS = {
    "og:title": "title",
    "twitter:title": "title",
    "og:description": "description",
    "description": "description",
    "author": "author",
    "og:image": "image",
    "og:url": "canonical_url",
}
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.I)
_META_KEY_RE = re.compile(r"""(?:property|name)=["']([^"']+)["']""", re.I)
_META_CONTENT_RE = re.compile(r"""content=["']([^"']*)["']""", re.I)
_PROJECT_TAG_RE = re.compile(r"project-show__tag--([a-z0-9_-]+)", re.I)


def _extract_meta(markup: str) -> dict[str, str]:
    """Pull the clean structured fields out of the page's <meta>/OG tags.

    Stardance server-renders an OG block with canonical title, author, and a
    "N devlogs · M hours worked" description — far cleaner than scraping the
    body, and fresher than the numbers baked into the visible DOM.
    """
    fields: dict[str, str] = {}
    for tag in _META_TAG_RE.findall(markup):
        key = _META_KEY_RE.search(tag)
        content = _META_CONTENT_RE.search(tag)
        if not key or not content:
            continue
        dest = _META_FIELDS.get(key.group(1).lower())
        if dest and dest not in fields:
            value = html.unescape(content.group(1)).strip()
            if value:
                fields[dest] = value
    if badge := _PROJECT_TAG_RE.search(markup):
        fields["project_type"] = badge.group(1).lower()
    return fields


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... (truncated, original length: {len(text)} chars)"


# Body markers left by bot-challenge interstitials (Cloudflare, Turnstile, etc.).
# These pages return HTTP 200 but contain no real app content, so a naive
# reachability check would falsely pass them.
_CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "enable javascript and cookies to continue",
    "cf-browser-verification",
    "cf_chl_opt",
    "challenge-platform",
    "/cdn-cgi/challenge-platform",
    "cf-turnstile",
    "turnstile",
    "attention required! | cloudflare",
    "please verify you are a human",
    "ddos protection by cloudflare",
    "ray id",
)


def _detect_challenge(response: httpx.Response, text: str | None = None) -> str | None:
    """Return a short reason if the response looks like a bot-challenge wall.

    Cloudflare/Turnstile challenges serve HTTP 200 (or 403/503) with a JS
    interstitial instead of the real page. We look at the ``cf-mitigated``
    header, the server banner on a blocking status, and known body markers.
    """
    headers = response.headers
    if headers.get("cf-mitigated", "").lower() == "challenge":
        return "cloudflare challenge (cf-mitigated header)"
    server = headers.get("server", "").lower()
    if "cloudflare" in server and response.status_code in (403, 429, 503):
        return f"cloudflare block (HTTP {response.status_code})"
    body = (text if text is not None else response.text or "").lower()
    if body:
        head = body[:6000]
        for marker in _CHALLENGE_MARKERS:
            if marker in head:
                return f"challenge interstitial (matched {marker!r})"
    return None


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


def _parse_package_url(url: str) -> tuple[str, str] | None:
    """Detect the registry and package name from a package URL.

    Handles the human-facing pages (npmjs.com/package/X, pypi.org/project/X,
    crates.io/crates/X) and the equivalent registry/API URLs. Package name case
    is preserved (npm scoped names keep their ``@scope/name`` form).
    """
    u = url.strip()
    npm = r"(@[^/?#]+/[^/?#]+|[^/?#]+)"
    if m := re.match(rf"https?://(?:www\.)?npmjs\.com/package/{npm}", u, re.I):
        return ("npm", m.group(1))
    if m := re.match(rf"https?://registry\.npmjs\.org/{npm}", u, re.I):
        return ("npm", m.group(1))
    if m := re.match(r"https?://pypi\.org/(?:project|pypi)/([^/?#]+)", u, re.I):
        return ("pypi", m.group(1))
    if m := re.match(r"https?://crates\.io/(?:crates|api/v1/crates)/([^/?#]+)", u, re.I):
        return ("crates", m.group(1))
    return None


class ReviewTools:
    """Bundle of review tools sharing one HTTP connection pool.

    Register on an agent with ``tools=review_tools.all()``.
    """

    def __init__(self, *, github_token: str = "", stardance_session: str = "") -> None:
        github_headers = {"Accept": "application/vnd.github+json", "User-Agent": "clanker/0.1"}
        if github_token:
            github_headers["Authorization"] = f"Bearer {github_token}"
        self._github = httpx.AsyncClient(
            base_url=GITHUB_API, timeout=TIMEOUT, headers=github_headers
        )
        self._web = httpx.AsyncClient(
            timeout=TIMEOUT, follow_redirects=True, headers=BROWSER_HEADERS
        )
        # Tolerate a pasted "name=value;" cookie; keep only the value. Sent solely
        # on stardance.hackclub.com requests, never on arbitrary demo fetches.
        raw = stardance_session.strip().rstrip(";").strip()
        self._stardance_session = raw.removeprefix(f"{STARDANCE_COOKIE_NAME}=").strip()

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
            self.review_check_package,
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
            # A bot-challenge wall answers 200 but shows no real app — surface it
            # instead of reporting a false "reachable".
            challenge = _detect_challenge(r)
            if challenge:
                flags.append("blocked_by_challenge")
                reachable = False
            return _ok(
                {
                    "url": url,
                    "final_url": str(r.url),
                    "status_code": r.status_code,
                    "reachable": reachable,
                    "content_type": r.headers.get("content-type", ""),
                    "challenge": challenge,
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
            challenge = _detect_challenge(r)
            if r.status_code >= 400 and not challenge:
                return _err(f"HTTP {r.status_code} fetching {url}")
            content_type = r.headers.get("content-type", "")
            text = _strip_html(r.text) if "text/html" in content_type else r.text
            if challenge:
                # The body is the interstitial, not the app — say so loudly so the
                # agent doesn't judge the demo on a bot wall.
                return json.dumps(
                    {
                        "ok": False,
                        "blocked_by_challenge": True,
                        "url": url,
                        "challenge": challenge,
                        "error": (
                            f"Page is behind a bot challenge ({challenge}); the returned "
                            "content is the interstitial, not the real app. Reachability "
                            "cannot be confirmed with a plain fetch."
                        ),
                        "text": _truncate(text, 2000),
                    }
                )
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
        """Fetch a Stardance project/ship page: structured meta + visible text.

        Pass the Stardance ship page from the packet
        (``/admin/certification/ship/{id}``) — that admin URL needs a Stardance
        login, so this sends the configured session cookie. Public
        ``/projects/{id}`` URLs also work but the cert's external_id is the *ship*
        id, not a project id, so never construct a /projects/ URL from it.

        Returns ``meta`` (title, author, project_type, and the canonical
        "N devlogs · M hours worked" description from the OG tags) plus the
        stripped devlog text. Fallback only — the packet's
        ai_declaration/updated_project fields are authoritative when present.

        A redirect to the site root is reported as an error
        (``redirected_away: true``) instead of silently returning the homepage:
        it means the login cookie is missing/expired, or the project was removed
        (e.g. banned for fraud) — a review signal worth flagging.
        """
        if not project_url or "stardance.hackclub.com" not in project_url:
            return _err(f"Not a Stardance URL: {project_url}")
        cookies = (
            {STARDANCE_COOKIE_NAME: self._stardance_session}
            if self._stardance_session
            else None
        )
        try:
            r = await self._web.get(project_url, cookies=cookies)
            if r.status_code >= 400:
                return _err(f"HTTP {r.status_code} fetching Stardance project")
            final_url = str(r.url)
            # An unauthenticated / removed page bounces to the site root ("" or "/").
            if not urlparse(final_url).path.strip("/"):
                authed = bool(self._stardance_session)
                reason = (
                    "the Stardance login cookie is missing or expired"
                    if not authed
                    else "the login cookie was rejected, or the project was removed "
                    "(e.g. banned for fraud)"
                )
                return json.dumps(
                    {
                        "ok": False,
                        "redirected_away": True,
                        "authenticated": authed,
                        "url": project_url,
                        "final_url": final_url,
                        "error": (
                            f"Requested {project_url} but was redirected to the site root "
                            f"({final_url}); {reason}. A vanished project is a review signal "
                            "— treat with suspicion once login is confirmed working."
                        ),
                    }
                )
            return json.dumps(
                {
                    "ok": True,
                    "url": project_url,
                    "final_url": final_url,
                    "meta": _extract_meta(r.text) or None,
                    "text": _truncate(_strip_html(r.text), 20000),
                }
            )
        except Exception as e:
            return _err(f"Failed to fetch Stardance project: {e}")

    async def review_check_package(self, url: str) -> str:
        """Verify a published package on npm, PyPI, or crates.io.

        Accepts a package page URL (``npmjs.com/package/X``,
        ``pypi.org/project/X``, ``crates.io/crates/X``, or the equivalent
        registry URL). Returns whether it exists, first/last publish dates,
        version count, and download counts where the registry exposes them.

        Use to verify "I published a package" claims: confirm it is real, check
        the first-publish date against the event window, and gauge whether it has
        real usage (downloads) or was only just published to tick a box.
        """
        parsed = _parse_package_url(url)
        if not parsed:
            return _err(f"Not a recognised package URL (npm/PyPI/crates.io): {url}")
        registry, name = parsed
        try:
            if registry == "npm":
                return await self._check_npm(name)
            if registry == "pypi":
                return await self._check_pypi(name)
            return await self._check_crates(name)
        except Exception as e:
            return _err(f"Failed to check package: {e}")

    async def _check_npm(self, name: str) -> str:
        r = await self._web.get(f"https://registry.npmjs.org/{name}")
        if r.status_code == 404:
            return _ok({"registry": "npm", "package": name, "exists": False})
        if r.status_code != 200:
            return _err(f"npm registry returned status {r.status_code}")
        data = r.json()
        times = data.get("time", {}) or {}
        repo = data.get("repository")
        repo_url = repo.get("url") if isinstance(repo, dict) else repo
        recent = None
        try:
            dr = await self._web.get(f"https://api.npmjs.org/downloads/point/last-month/{name}")
            if dr.status_code == 200:
                recent = dr.json().get("downloads")
        except Exception:
            pass
        return _ok(
            {
                "registry": "npm",
                "package": name,
                "exists": True,
                "latest_version": (data.get("dist-tags") or {}).get("latest"),
                "first_published": times.get("created"),
                "last_published": times.get("modified"),
                "versions_count": len(data.get("versions", {}) or {}),
                "downloads_last_month": recent,
                "description": data.get("description"),
                "homepage": data.get("homepage"),
                "repository": repo_url,
            }
        )

    async def _check_pypi(self, name: str) -> str:
        r = await self._web.get(f"https://pypi.org/pypi/{name}/json")
        if r.status_code == 404:
            return _ok({"registry": "pypi", "package": name, "exists": False})
        if r.status_code != 200:
            return _err(f"PyPI returned status {r.status_code}")
        data = r.json()
        info = data.get("info", {}) or {}
        releases = data.get("releases", {}) or {}
        uploads = sorted(
            f.get("upload_time_iso_8601") or f.get("upload_time")
            for files in releases.values()
            for f in files
            if f.get("upload_time_iso_8601") or f.get("upload_time")
        )
        project_urls = info.get("project_urls") or {}
        return _ok(
            {
                "registry": "pypi",
                "package": name,
                "exists": True,
                "latest_version": info.get("version"),
                "first_published": uploads[0] if uploads else None,
                "last_published": uploads[-1] if uploads else None,
                "versions_count": len(releases),
                "downloads_last_month": None,  # not exposed by this API
                "description": info.get("summary"),
                "author": info.get("author") or info.get("author_email"),
                "homepage": info.get("home_page") or project_urls.get("Homepage"),
                "repository": project_urls.get("Source") or project_urls.get("Repository"),
            }
        )

    async def _check_crates(self, name: str) -> str:
        r = await self._web.get(f"https://crates.io/api/v1/crates/{name}")
        if r.status_code == 404:
            return _ok({"registry": "crates", "package": name, "exists": False})
        if r.status_code != 200:
            return _err(f"crates.io returned status {r.status_code}")
        data = r.json()
        crate = data.get("crate", {}) or {}
        return _ok(
            {
                "registry": "crates",
                "package": name,
                "exists": True,
                "latest_version": crate.get("newest_version") or crate.get("max_version"),
                "first_published": crate.get("created_at"),
                "last_published": crate.get("updated_at"),
                "versions_count": len(data.get("versions", []) or []),
                "downloads_total": crate.get("downloads"),
                "downloads_recent": crate.get("recent_downloads"),
                "description": crate.get("description"),
                "homepage": crate.get("homepage"),
                "repository": crate.get("repository"),
            }
        )
