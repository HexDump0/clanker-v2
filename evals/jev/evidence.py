"""Deterministically fetch code excerpts for AI-usage judgments (no LLM involved).

Reviewers mostly reject for AI-heavy code/CSS ("looks like every other AI-made site"), so
Jev needs to see some actual code. Code picks the likely styling and main source files from
the frozen packet's file tree and reads them at the submission-time commit (pinned).

    JEV_DATASET=dev uv run python evals/jev/evidence.py
"""

from __future__ import annotations

import asyncio
import re

import httpx
from common import CODE, TRACES, append_jsonl, read_jsonl

from clanker.config import load_settings

EXCERPT_CHARS = 3_500
MAX_FILES = 3
STYLE_NAMES = ("style.css", "styles.css", "index.css", "globals.css", "global.css", "app.css", "main.css")
MAIN_NAMES = (
    "script.js", "main.js", "app.js", "index.js", "app.jsx", "app.tsx", "main.tsx", "main.py",
    "app.py", "bot.py", "index.ts", "main.ts", "main.rs", "main.go", "main.cpp", "main.c",
    "program.cs", "main.java", "main.dart", "main.gd", "game.js", "index.html",
)
CODE_EXT = (".css", ".scss", ".js", ".ts", ".tsx", ".jsx", ".py", ".rs", ".go", ".java", ".kt",
            ".swift", ".cs", ".cpp", ".c", ".dart", ".gd", ".lua", ".vue", ".svelte", ".html")
SKIP = re.compile(r"(^|/)(node_modules|dist|build|vendor|\.next|venv|\.venv|assets/lib)/|\.min\.|lock", re.I)


def pick_files(tree: list[str]) -> list[str]:
    files = [f for f in tree if not SKIP.search(f)]
    by_name = {f.rsplit("/", 1)[-1].lower(): f for f in sorted(files, key=len)}
    chosen: list[str] = []
    for names in (STYLE_NAMES, MAIN_NAMES):
        for n in names:
            if n in by_name and by_name[n] not in chosen:
                chosen.append(by_name[n])
                break
    for f in sorted(files, key=lambda x: (x.count("/"), x)):
        if len(chosen) >= MAX_FILES:
            break
        if f.lower().endswith(CODE_EXT) and f not in chosen:
            chosen.append(f)
    return chosen[:MAX_FILES]


async def main() -> None:
    settings = load_settings()
    done = {r["trace_id"] for r in read_jsonl(CODE)}
    traces = [t for t in read_jsonl(TRACES) if t["trace_id"] not in done]
    print(f"{len(traces)} traces need code excerpts")
    headers = {"User-Agent": "clanker-eval", "Accept": "application/vnd.github.raw+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    sem = asyncio.Semaphore(6)

    async with httpx.AsyncClient(base_url="https://api.github.com", headers=headers, timeout=20) as gh:

        async def one(t: dict) -> None:
            prompt = t["messages"][0]["parts"][0]["content"]
            repo = re.search(r"^- Repo URL: https://github\.com/([^/\s]+)/([^/\s#?]+)", prompt, re.M)
            sha = re.search(r"^- ([0-9a-f]{7,40}) \d{4}-\d{2}-\d{2}T", prompt, re.M)
            tree = re.findall(r"^  - (.+)$", prompt.split("## Repo structure", 1)[-1].split("\n## ", 1)[0], re.M)
            excerpts = []
            if repo and tree:
                owner, name = repo.group(1), repo.group(2).removesuffix(".git")
                async with sem:
                    for path in pick_files(tree):
                        r = await gh.get(
                            f"/repos/{owner}/{name}/contents/{path}",
                            params={"ref": sha.group(1)} if sha else {},
                        )
                        if r.status_code == 200:
                            text = r.text
                            excerpts.append({
                                "path": path,
                                "total_chars": len(text),
                                "excerpt": text[:EXCERPT_CHARS],
                            })
            append_jsonl(CODE, {"trace_id": t["trace_id"], "files": excerpts})

        await asyncio.gather(*(one(t) for t in traces))
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
