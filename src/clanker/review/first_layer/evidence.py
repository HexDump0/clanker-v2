"""Extra first-layer evidence, gathered by code plus one narrow vision call. No agent.

- Code excerpts: real file sizes from the repo tree (GitHub, GitLab, Gitea/Forgejo) at the
  submission commit; the largest
  stylesheet, UI file and logic file; head + middle slice of each (AI-look lives throughout
  a file, not just the top).
- Release assets that existed before the review (for demo-format checks).
- Banner label: the Stardance banner image goes to a cheap vision model with a one-label
  question ("screenshot of the running project" vs code / logo / AI art / unrelated).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

import httpx
from pydantic_ai import Agent, BinaryContent

from clanker.config import Settings
from clanker.forges import Repo, parse_repo
from clanker.llm import build_model, build_routing_model_settings
from clanker.review.first_layer.facts import CUTOFF

HEAD, MIDDLE = 2_500, 1_500
MAX_TREE_PAGES = 10  # GitLab: 100 entries a page; Gitea: 1000
MAX_SIZED_PATHS = 300  # GitLab GraphQL size lookup
TREE_PATHS = 400  # file list handed to Jev when the packet has no GitHub tree
CUTOFF_ISO = f"{CUTOFF.isoformat()}T00:00:00Z"  # Stardance start (June 1, 2026)
MAX_IMAGE_BYTES = 8_000_000

SKIP = re.compile(
    r"(^|/)(node_modules|dist|build|out|vendor|\.next|venv|\.venv|site-packages|coverage|"
    r"public/lib|static/lib|libs?)/|\.min\.|bootstrap|tailwind\.(css|config)|normalize\.css|"
    r"lock|\.d\.ts$|(^|/)(test|tests|__tests__)/|\.(test|spec)\.|config\.",
    re.I,
)
STYLE = (".css", ".scss", ".sass", ".less")
UI = (".jsx", ".tsx", ".vue", ".svelte", ".html")
LOGIC = (".js", ".ts", ".py", ".rs", ".go", ".java", ".kt", ".swift", ".cs", ".cpp", ".c",
         ".dart", ".gd", ".lua", ".rb", ".php")  # fmt: skip
BANNER_LABELS = {
    "project_screenshot": "a screenshot or photo of the actual project running/in action",
    "code_screenshot": "a screenshot of source code or an editor",
    "logo_or_text": "a logo, title card, icon, or mostly text graphic",
    "ai_generated_art": "AI-generated illustration or art rather than the real project",
    "unrelated": "an unrelated photo, meme, or image not showing the project",
    "unclear": "cannot tell",
}
BANNER_PROMPT = (
    "This is the banner image of a software/hardware project submission. Which ONE label fits "
    "best? Reply with only the label.\n"
    + "\n".join(f"- {k}: {v}" for k, v in BANNER_LABELS.items())
)


def excerpt(text: str) -> str:
    if len(text) <= HEAD + MIDDLE:
        return text
    mid = len(text) // 2
    return text[:HEAD] + "\n/* … */\n" + text[mid : mid + MIDDLE]


def pick_files(blobs: list[tuple[str, int]]) -> list[str]:
    """Largest non-vendored stylesheet, UI file and logic file."""
    files = [(p, s) for p, s in blobs if not SKIP.search(p)]
    chosen: list[str] = []
    for exts in (STYLE, UI, LOGIC):
        candidates = sorted(
            (f for f in files if f[0].lower().endswith(exts) and f[0] not in chosen),
            key=lambda f: -f[1],
        )
        if candidates:
            chosen.append(candidates[0][0])
    return chosen


def create_banner_agent(settings: Settings) -> Agent:
    model_settings = build_routing_model_settings(settings)
    # One-word perception task: no reasoning tokens needed.
    model_settings["openrouter_reasoning"] = {"enabled": False}
    model_settings["max_tokens"] = 20
    return Agent(
        build_model(settings, settings.banner_model_name),
        instructions="You classify project banner images. Answer with one label only.",
        model_settings=model_settings,
    )


async def classify_banner(url: str, web: httpx.AsyncClient, vision: Agent) -> str:
    img = await web.get(url)
    ctype = img.headers.get("content-type", "").split(";")[0]
    if (
        img.status_code != 200
        or not ctype.startswith("image/")
        or len(img.content) >= MAX_IMAGE_BYTES
    ):
        return f"unavailable:{img.status_code}:{ctype}"
    res = await vision.run([BANNER_PROMPT, BinaryContent(data=img.content, media_type=ctype)])
    text = res.output.strip().lower()
    return next((k for k in BANNER_LABELS if k in text), "unclear")


def submission_commit(prompt: str) -> str | None:
    """Newest commit in the packet = repo state at submission time."""
    m = re.search(r"^- ([0-9a-f]{7,40}) \d{4}-\d{2}-\d{2}T", prompt, re.M)
    return m.group(1) if m else None


async def gather_evidence(
    prompt: str,
    *,
    cutoff: str,
    gh: httpx.AsyncClient,
    web: httpx.AsyncClient,
    vision: Agent | None,
) -> dict[str, Any]:
    """Evidence for one packet. Failures are recorded as data, never raised.

    ``cutoff`` is an ISO timestamp: release assets uploaded after it are ignored. GitHub,
    GitLab and Gitea/Forgejo (Codeberg) repos get code excerpts and release assets; other
    forges get neither (the Jev code questions then answer "not AI" by design).
    """
    out: dict[str, Any] = {"files": [], "release_assets": None, "banner": None}
    m = re.search(r"^- Repo URL: (\S+)", prompt, re.M)
    repo = parse_repo(m.group(1) if m else None)
    sha = submission_commit(prompt)
    try:
        if repo is not None and repo.kind == "github":
            await _github_evidence(repo, sha, cutoff, gh, out)
        elif repo is not None and repo.kind == "gitlab":
            await _gitlab_evidence(repo, sha or "HEAD", cutoff, web, out)
        elif repo is not None and repo.kind == "gitea":
            await _gitea_evidence(repo, sha or "HEAD", cutoff, web, out)
    except Exception as exc:
        out["github_error"] = str(exc)[:200]

    banner = re.search(r"^- banner_url: (\S+)", prompt, re.M)
    if banner and vision is not None:
        try:
            out["banner"] = await classify_banner(banner.group(1), web, vision)
        except Exception as exc:
            out["banner"] = f"error:{type(exc).__name__}"
    return out


async def _add_files(
    blobs: list[tuple[str, int]], out: dict[str, Any], read: Callable[[str], Awaitable[str | None]]
) -> None:
    """Shared by every forge: count code files, pick and excerpt the three to show Jev."""
    out["tree_code_files"] = sum(p.lower().endswith(STYLE + UI + LOGIC) for p, _ in blobs)
    out["tree_paths"] = [p for p, _ in blobs[:TREE_PATHS]]
    for path in pick_files(blobs):
        text = await read(path)
        if text is not None:
            out["files"].append({"path": path, "total_chars": len(text), "excerpt": excerpt(text)})


async def _github_evidence(
    repo: Repo, sha: str | None, cutoff: str, gh: httpx.AsyncClient, out: dict[str, Any]
) -> None:
    base = f"/repos/{repo.path}"
    commit = await gh.get(f"{base}/commits/{sha or 'HEAD'}")
    if commit.status_code == 200:
        full = commit.json()["sha"]
        tree = await gh.get(
            f"{base}/git/trees/{commit.json()['commit']['tree']['sha']}",
            params={"recursive": "1"},
        )
        if tree.status_code == 200:

            async def read(path: str) -> str | None:
                r = await gh.get(
                    f"{base}/contents/{path}",
                    params={"ref": full},
                    headers={"Accept": "application/vnd.github.raw+json"},
                )
                return r.text if r.status_code == 200 else None

            blobs = [
                (e["path"], e.get("size", 0))
                for e in tree.json().get("tree", [])
                if e.get("type") == "blob"
            ]
            await _add_files(blobs, out, read)
        out["history"] = await _github_history(gh, base, full, repo.path.split("/")[0])
    releases = await gh.get(f"{base}/releases", params={"per_page": 20})
    if releases.status_code == 200:
        out["release_assets"] = [
            a["name"]
            for rel in releases.json()
            for a in rel.get("assets", [])
            if (a.get("created_at") or "") <= cutoff
        ]


async def _gitlab_evidence(
    repo: Repo, ref: str, cutoff: str, web: httpx.AsyncClient, out: dict[str, Any]
) -> None:
    api = f"https://{repo.host}/api/v4/projects/{quote(repo.path, safe='')}"
    paths: list[str] = []
    for page in range(1, MAX_TREE_PAGES + 1):
        r = await web.get(
            f"{api}/repository/tree",
            params={"recursive": "true", "per_page": 100, "ref": ref, "page": page},
        )
        if r.status_code != 200:
            break
        items = r.json()
        paths += [e["path"] for e in items if e.get("type") == "blob"]
        if len(items) < 100:
            break
    if paths:
        # The REST tree has no sizes; GraphQL returns them for many paths in one request.
        candidates = [p for p in paths if p.lower().endswith(STYLE + UI + LOGIC)]
        candidates = [p for p in candidates if not SKIP.search(p)][:MAX_SIZED_PATHS]
        sizes: dict[str, int] = {}
        if candidates:
            g = await web.post(
                f"https://{repo.host}/api/graphql",
                json={
                    "query": "query($p: ID!, $paths: [String!]!, $ref: String) { project("
                    "fullPath: $p) { repository { blobs(paths: $paths, ref: $ref) { nodes "
                    "{ path size } } } } }",
                    "variables": {"p": repo.path, "paths": candidates, "ref": ref},
                },
            )
            if g.status_code == 200:
                project = (g.json().get("data") or {}).get("project") or {}
                nodes = ((project.get("repository") or {}).get("blobs") or {}).get("nodes") or []
                sizes = {n["path"]: int(n.get("size") or 0) for n in nodes}

        async def read(path: str) -> str | None:
            r = await web.get(
                f"{api}/repository/files/{quote(path, safe='')}/raw", params={"ref": ref}
            )
            return r.text if r.status_code == 200 else None

        await _add_files([(p, sizes.get(p, 0)) for p in paths], out, read)
    out["history"] = await _gitlab_history(web, api, ref)
    releases = await web.get(f"{api}/releases", params={"per_page": 20})
    if releases.status_code == 200:
        out["release_assets"] = [
            link["name"]
            for rel in releases.json()
            if (rel.get("released_at") or rel.get("created_at") or "") <= cutoff
            for link in (rel.get("assets") or {}).get("links", [])
        ]


async def _gitea_evidence(
    repo: Repo, ref: str, cutoff: str, web: httpx.AsyncClient, out: dict[str, Any]
) -> None:
    api = f"https://{repo.host}/api/v1/repos/{repo.path}"
    blobs: list[tuple[str, int]] = []
    for page in range(1, MAX_TREE_PAGES + 1):
        r = await web.get(
            f"{api}/git/trees/{ref}", params={"recursive": "true", "per_page": 1000, "page": page}
        )
        if r.status_code != 200:
            break
        data = r.json()
        blobs += [
            (e["path"], e.get("size", 0)) for e in data.get("tree") or [] if e.get("type") == "blob"
        ]
        if not data.get("truncated"):
            break
    if blobs:

        async def read(path: str) -> str | None:
            r = await web.get(f"{api}/raw/{quote(path)}", params={"ref": ref})
            return r.text if r.status_code == 200 else None

        await _add_files(blobs, out, read)
    releases = await web.get(f"{api}/releases", params={"limit": 20})
    if releases.status_code == 200:
        out["release_assets"] = [
            a["name"]
            for rel in releases.json()
            for a in rel.get("assets") or []
            if (a.get("created_at") or "") <= cutoff
        ]


def _page_count(r: httpx.Response) -> int:
    """Total items of a per_page=1 listing, from its rel="last" link."""
    last = r.links.get("last", {}).get("url")
    m = re.search(r"[?&]page=(\d+)", last or "")
    return int(m.group(1)) if m else len(r.json())


async def _github_history(
    gh: httpx.AsyncClient, base: str, sha: str, owner: str
) -> dict[str, Any] | None:
    """Commit counts around the event cutoff (the packet only carries the latest 30).

    Only the owner's commits count as their pre-event work: a template or upstream
    history by other authors isn't theirs. Commits with no linked GitHub account count
    as the owner's (most beginners haven't linked their git email).
    """
    total = await gh.get(f"{base}/commits", params={"sha": sha, "per_page": 1})
    pre = await gh.get(
        f"{base}/commits", params={"sha": sha, "until": CUTOFF_ISO, "per_page": 100}
    )
    if total.status_code != 200 or pre.status_code != 200:
        return None
    commits = pre.json()
    own = [
        c
        for c in commits
        if ((c.get("author") or {}).get("login") or owner).lower() == owner.lower()
    ]
    dates = sorted((c.get("commit") or {}).get("author", {}).get("date") or "" for c in own)
    return {
        "total_commits": _page_count(total),
        "pre_cutoff_commits": len(commits),  # capped at 100
        "pre_cutoff_own_commits": len(own),
        "oldest_own_commit": (dates[0][:10] if dates and dates[0] else None),
    }


async def _gitlab_history(web: httpx.AsyncClient, api: str, ref: str) -> dict[str, Any] | None:
    """GitLab has no account links on commits, so every pre-cutoff commit counts."""
    total = await web.get(f"{api}/repository/commits", params={"ref_name": ref, "per_page": 1})
    pre = await web.get(
        f"{api}/repository/commits",
        params={"ref_name": ref, "until": CUTOFF_ISO, "per_page": 100},
    )
    if total.status_code != 200 or pre.status_code != 200:
        return None
    commits = pre.json()
    dates = sorted(c.get("authored_date") or "" for c in commits)
    return {
        "total_commits": int(total.headers.get("x-total") or len(total.json())),
        "pre_cutoff_commits": len(commits),
        "pre_cutoff_own_commits": len(commits),
        "oldest_own_commit": (dates[0][:10] if dates and dates[0] else None),
    }
