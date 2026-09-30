"""Richer first-layer evidence, gathered by code plus one narrow vision call. No agent.

Per trace:
- code excerpts: real file sizes from the GitHub tree at the submission commit; take the
  largest stylesheet, UI file, and logic file; head + middle slice of each (AI-look lives
  throughout a file, not just the top);
- release assets that existed before the review (for demo format checks);
- banner classification: the Stardance banner image goes to a cheap vision model with
  a one-label question ("screenshot of the running project" vs code/logo/AI art/...).

    JEV_DATASET=dev uv run python evals/jev/evidence2.py
"""

from __future__ import annotations

import asyncio
import os
import re

import httpx
from common import DATA, TRACES, append_jsonl, read_jsonl
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from clanker.config import load_settings

EVIDENCE = DATA / "evidence2.jsonl"
# Cheap, image-capable, 30+ upstream providers (so no single provider can rate-limit us).
VISION_MODEL = os.environ.get("JEV_BANNER_MODEL", "deepseek/deepseek-v4.1-flash")
HEAD, MIDDLE = 2_500, 1_500

SKIP = re.compile(
    r"(^|/)(node_modules|dist|build|out|vendor|\.next|venv|\.venv|site-packages|coverage|"
    r"public/lib|static/lib|libs?)/|\.min\.|bootstrap|tailwind\.(css|config)|normalize\.css|"
    r"lock|\.d\.ts$|(^|/)(test|tests|__tests__)/|\.(test|spec)\.|config\.",
    re.I,
)
STYLE = (".css", ".scss", ".sass", ".less")
UI = (".jsx", ".tsx", ".vue", ".svelte", ".html")
LOGIC = (".js", ".ts", ".py", ".rs", ".go", ".java", ".kt", ".swift", ".cs", ".cpp", ".c",
         ".dart", ".gd", ".lua", ".rb", ".php")
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


def _slice(text: str) -> str:
    if len(text) <= HEAD + MIDDLE:
        return text
    mid = len(text) // 2
    return text[:HEAD] + "\n/* … */\n" + text[mid: mid + MIDDLE]


def pick(blobs: list[tuple[str, int]]) -> list[str]:
    files = [(p, s) for p, s in blobs if not SKIP.search(p)]
    chosen = []
    for exts in (STYLE, UI, LOGIC):
        cands = sorted((f for f in files if f[0].lower().endswith(exts) and f[0] not in chosen),
                       key=lambda f: -f[1])
        if cands:
            chosen.append(cands[0][0])
    return chosen


async def gather(t: dict, gh: httpx.AsyncClient, web: httpx.AsyncClient, vision: Agent) -> dict:
    prompt = t["messages"][0]["parts"][0]["content"]
    out: dict = {"trace_id": t["trace_id"], "files": [], "release_assets": None, "banner": None}
    repo = re.search(r"^- Repo URL: https://github\.com/([^/\s]+)/([^/\s#?]+)", prompt, re.M)
    sha = re.search(r"^- ([0-9a-f]{7,40}) \d{4}-\d{2}-\d{2}T", prompt, re.M)
    if repo:
        owner, name = repo.group(1), repo.group(2).removesuffix(".git")
        base = f"/repos/{owner}/{name}"
        try:
            ref = sha.group(1) if sha else "HEAD"
            c = await gh.get(f"{base}/commits/{ref}")
            if c.status_code == 200:
                full = c.json()["sha"]
                tree = await gh.get(f"{base}/git/trees/{c.json()['commit']['tree']['sha']}",
                                    params={"recursive": "1"})
                if tree.status_code == 200:
                    blobs = [(e["path"], e.get("size", 0)) for e in tree.json().get("tree", [])
                             if e.get("type") == "blob"]
                    out["tree_code_files"] = sum(p.lower().endswith(STYLE + UI + LOGIC) for p, _ in blobs)
                    for path in pick(blobs):
                        r = await gh.get(f"{base}/contents/{path}", params={"ref": full},
                                         headers={"Accept": "application/vnd.github.raw+json"})
                        if r.status_code == 200:
                            out["files"].append({"path": path, "total_chars": len(r.text),
                                                 "excerpt": _slice(r.text)})
            rel = await gh.get(f"{base}/releases", params={"per_page": 20})
            if rel.status_code == 200:
                cutoff = t["start_timestamp"]
                out["release_assets"] = [
                    a["name"] for r in rel.json() for a in r.get("assets", [])
                    if (a.get("created_at") or "") <= cutoff
                ]
        except Exception as exc:  # evidence failures are data, not fatal
            out["github_error"] = str(exc)[:200]

    banner = re.search(r"^- banner_url: (\S+)", prompt, re.M)
    if banner:
        try:
            out["banner"] = await classify_banner(banner.group(1), web, vision)
        except Exception as exc:
            out["banner"] = f"error:{type(exc).__name__}"
    return out


def banner_agent(api_key: str) -> Agent:
    return Agent(
        OpenRouterModel(VISION_MODEL, provider=OpenRouterProvider(api_key=api_key)),
        instructions="You classify project banner images. Answer with one label only.",
        # One-word perception task: no reasoning tokens needed.
        model_settings={"openrouter_reasoning": {"enabled": False}, "max_tokens": 20},
    )


async def classify_banner(url: str, web: httpx.AsyncClient, vision: Agent) -> str:
    img = await web.get(url)
    ctype = img.headers.get("content-type", "").split(";")[0]
    if img.status_code != 200 or not ctype.startswith("image/") or len(img.content) >= 8_000_000:
        return f"unavailable:{img.status_code}:{ctype}"
    res = await vision.run([BANNER_PROMPT, BinaryContent(data=img.content, media_type=ctype)])
    text = res.output.strip().lower()
    return next((k for k in BANNER_LABELS if k in text), "unclear")


async def main() -> None:
    settings = load_settings()
    done = {r["trace_id"] for r in read_jsonl(EVIDENCE)}
    traces = [t for t in read_jsonl(TRACES) if t["trace_id"] not in done]
    print(f"{len(traces)} traces need evidence")
    vision = banner_agent(settings.openrouter_api_key)
    gh_headers = {"User-Agent": "clanker-eval", "Accept": "application/vnd.github+json"}
    if settings.github_token:
        gh_headers["Authorization"] = f"Bearer {settings.github_token}"
    sem = asyncio.Semaphore(4)
    async with (
        httpx.AsyncClient(base_url="https://api.github.com", headers=gh_headers, timeout=20) as gh,
        httpx.AsyncClient(follow_redirects=True, timeout=30) as web,
    ):
        async def one(t: dict) -> None:
            async with sem:
                append_jsonl(EVIDENCE, await gather(t, gh, web, vision))

        await asyncio.gather(*(one(t) for t in traces))
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
