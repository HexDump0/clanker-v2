"""Re-run only the banner check with the current JEV_BANNER_MODEL, updating evidence2.jsonl in
place (the previous label is kept as `banner_prev`, the model as `banner_model`).

    JEV_DATASET=holdout uv run python evals/jev/relabel_banners.py
"""

from __future__ import annotations

import asyncio
import json
import re

import httpx
from common import DATA, TRACES, read_jsonl
from evidence2 import VISION_MODEL, banner_agent, classify_banner

from clanker.config import load_settings

EVIDENCE = DATA / "evidence2.jsonl"


async def main() -> None:
    settings = load_settings()
    traces = {t["trace_id"]: t for t in read_jsonl(TRACES)}
    rows = list(read_jsonl(EVIDENCE))
    vision = banner_agent(settings.openrouter_api_key)
    sem = asyncio.Semaphore(6)

    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as web:

        async def one(row: dict) -> None:
            if row.get("banner_model") == VISION_MODEL:
                return
            prompt = traces[row["trace_id"]]["messages"][0]["parts"][0]["content"]
            banner = re.search(r"^- banner_url: (\S+)", prompt, re.M)
            if not banner:
                return
            async with sem:
                try:
                    label = await classify_banner(banner.group(1), web, vision)
                except Exception as exc:
                    label = f"error:{type(exc).__name__}"
            row["banner_prev"], row["banner"], row["banner_model"] = row.get("banner"), label, VISION_MODEL

        await asyncio.gather(*(one(r) for r in rows))
    EVIDENCE.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    changed = sum(r.get("banner_prev") != r.get("banner") for r in rows if "banner_model" in r)
    print(f"relabelled {sum('banner_model' in r for r in rows)} banners with {VISION_MODEL}; "
          f"{changed} labels changed")


if __name__ == "__main__":
    asyncio.run(main())
