"""Extra first-layer evidence, gathered by code plus one narrow vision call. No agent.

- Code excerpts: real file sizes from the GitHub tree at the submission commit; the largest
  stylesheet, UI file and logic file; head + middle slice of each (AI-look lives throughout
  a file, not just the top).
- Release assets that existed before the review (for demo-format checks).
- Banner label: the Stardance banner image goes to a cheap vision model with a one-label
  question ("screenshot of the running project" vs code / logo / AI art / unrelated).
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from pydantic_ai import Agent, BinaryContent

from clanker.config import Settings
from clanker.llm import build_model, build_routing_model_settings

HEAD, MIDDLE = 2_500, 1_500
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

    ``cutoff`` is an ISO timestamp: release assets uploaded after it are ignored.
    """
    out: dict[str, Any] = {"files": [], "release_assets": None, "banner": None}
    repo = re.search(r"^- Repo URL: https://github\.com/([^/\s]+)/([^/\s#?]+)", prompt, re.M)
    sha = submission_commit(prompt)
    if repo:
        owner, name = repo.group(1), repo.group(2).removesuffix(".git")
        base = f"/repos/{owner}/{name}"
        try:
            commit = await gh.get(f"{base}/commits/{sha or 'HEAD'}")
            if commit.status_code == 200:
                full = commit.json()["sha"]
                tree = await gh.get(
                    f"{base}/git/trees/{commit.json()['commit']['tree']['sha']}",
                    params={"recursive": "1"},
                )
                if tree.status_code == 200:
                    blobs = [
                        (e["path"], e.get("size", 0))
                        for e in tree.json().get("tree", [])
                        if e.get("type") == "blob"
                    ]
                    out["tree_code_files"] = sum(
                        p.lower().endswith(STYLE + UI + LOGIC) for p, _ in blobs
                    )
                    for path in pick_files(blobs):
                        r = await gh.get(
                            f"{base}/contents/{path}",
                            params={"ref": full},
                            headers={"Accept": "application/vnd.github.raw+json"},
                        )
                        if r.status_code == 200:
                            out["files"].append(
                                {
                                    "path": path,
                                    "total_chars": len(r.text),
                                    "excerpt": excerpt(r.text),
                                }
                            )
            releases = await gh.get(f"{base}/releases", params={"per_page": 20})
            if releases.status_code == 200:
                out["release_assets"] = [
                    a["name"]
                    for rel in releases.json()
                    for a in rel.get("assets", [])
                    if (a.get("created_at") or "") <= cutoff
                ]
        except Exception as exc:
            out["github_error"] = str(exc)[:200]

    banner = re.search(r"^- banner_url: (\S+)", prompt, re.M)
    if banner and vision is not None:
        try:
            out["banner"] = await classify_banner(banner.group(1), web, vision)
        except Exception as exc:
            out["banner"] = f"error:{type(exc).__name__}"
    return out
