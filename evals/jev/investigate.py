"""Space Bunny (free stealth model on OpenRouter) investigates; it does NOT decide.

Starts from the frozen production packet and uses Clanker's real read-only tools to gather
evidence for the rubric. The output (tool results plus a neutral findings list) becomes Jev's
`bunny` state. GitHub file reads are pinned to the newest commit in the frozen packet, so
later pushes to the repo don't leak in. Live demo pages and releases can still drift; that
is noted in the report.

    uv run python evals/jev/investigate.py --limit 60 --concurrency 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time

import httpx
from common import DATA, TRACES, append_jsonl, read_jsonl
from pydantic_ai import Agent, UsageLimits
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from clanker.config import load_settings
from clanker.review.tools import ReviewTools

BUNNY = DATA / "bunny.jsonl"
MODEL = "stealth/space-bunny-alpha"
FILE_LIMIT = 12_000

INSTRUCTIONS = """\
You are the evidence investigator for a Hack Club Stardance project review. Another system
makes the approve/reject decision; you only gather and report evidence.

You receive a submission packet (submission fields, commits, file tree, Stardance page, demo
render, README). Do not re-fetch what the packet already contains. Use your tools only for
what it lacks, typically:
- read 1-4 key source files to confirm the project is real, matches the README/description,
  and whether it has login/accounts or hardcoded demo credentials;
- for desktop/CLI/mobile projects, check GitHub releases for real binaries;
- if the demo is not a normal website, check that the link works and what it is;
- for "published package" claims, check the registry.
Be efficient: batch independent tool calls in the same step, and stop after at most 3 steps.

Finish with a short factual findings list (one line each): what you checked and what you
observed. No verdict, no recommendation, no speculation beyond the evidence.
"""


def _repo(prompt: str) -> tuple[str, str] | None:
    m = re.search(r"^- Repo URL: https://github\.com/([^/\s]+)/([^/\s#?]+)", prompt, re.M)
    return (m.group(1), m.group(2).removesuffix(".git")) if m else None


def _pin_sha(prompt: str) -> str | None:
    """Newest commit in the frozen packet = repo state at submission time."""
    m = re.search(r"^- ([0-9a-f]{7,40}) \d{4}-\d{2}-\d{2}T", prompt, re.M)
    return m.group(1) if m else None


async def investigate(trace: dict, tools: ReviewTools, gh: httpx.AsyncClient, model) -> dict:
    prompt = trace["messages"][0]["parts"][0]["content"]
    repo = _repo(prompt)
    sha = _pin_sha(prompt)

    async def read_repo_file(file_path: str) -> str:
        """Read one file from the submitted repository, as it was at submission time."""
        if not repo:
            return json.dumps({"ok": False, "error": "no GitHub repo URL in the packet"})
        params = {"ref": sha} if sha else {}
        r = await gh.get(
            f"/repos/{repo[0]}/{repo[1]}/contents/{file_path.lstrip('/')}",
            params=params,
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        if r.status_code != 200:
            return json.dumps({"ok": False, "path": file_path, "status": r.status_code})
        text = r.text
        body = text if len(text) <= FILE_LIMIT else text[:FILE_LIMIT] + "\n...[truncated]"
        return json.dumps({"ok": True, "path": file_path, "pinned_ref": sha, "content": body})

    agent = Agent(
        model,
        instructions=INSTRUCTIONS,
        tools=[
            read_repo_file,
            tools.get_github_releases,
            tools.check_url,
            tools.fetch_page_text,
            tools.check_package,
        ],
    )
    started = time.perf_counter()
    result = await agent.run(prompt, usage_limits=UsageLimits(request_limit=6))
    calls: dict[str, dict] = {}
    steps = []
    for msg in result.all_messages():
        for part in msg.parts:
            if isinstance(part, ToolCallPart):
                calls[part.tool_call_id] = {"tool": part.tool_name, "args": part.args}
            elif isinstance(part, ToolReturnPart):
                content = part.content if isinstance(part.content, str) else json.dumps(part.content)
                steps.append({**calls.get(part.tool_call_id, {"tool": part.tool_name}), "result": content})
    usage = result.usage
    return {
        "trace_id": trace["trace_id"],
        "cert_id": trace["cert_id"],
        "latency_s": round(time.perf_counter() - started, 2),
        "requests": usage.requests,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "pinned_sha": sha,
        "steps": steps,
        "findings": result.output,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()

    done = {r["trace_id"] for r in read_jsonl(BUNNY) if "error" not in r}
    traces = [t for t in read_jsonl(TRACES) if t["trace_id"] not in done]
    if args.limit:
        traces = traces[: args.limit]
    print(f"{len(traces)} traces to investigate")

    settings = load_settings()
    model = OpenRouterModel(MODEL, provider=OpenRouterProvider(api_key=settings.openrouter_api_key))
    tools = ReviewTools(github_token=settings.github_token)
    gh_headers = {"User-Agent": "clanker-eval"}
    if settings.github_token:
        gh_headers["Authorization"] = f"Bearer {settings.github_token}"
    sem = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient(base_url="https://api.github.com", headers=gh_headers, timeout=20) as gh:

        async def one(trace: dict) -> None:
            async with sem:
                for attempt in range(4):
                    try:
                        row = await investigate(trace, tools, gh, model)
                        append_jsonl(BUNNY, row)
                        print(f"ok {trace['cert_id']} {row['latency_s']}s {len(row['steps'])} tools")
                        return
                    except Exception as exc:
                        msg = f"{type(exc).__name__}: {exc}"
                        if "429" in msg and attempt < 3:
                            await asyncio.sleep(20 * (attempt + 1))
                            continue
                        append_jsonl(BUNNY, {"trace_id": trace["trace_id"], "cert_id": trace["cert_id"], "error": msg[:500]})
                        print("ERR", trace["cert_id"], msg[:200])
                        return

        await asyncio.gather(*(one(t) for t in traces))
    await tools.aclose()


if __name__ == "__main__":
    asyncio.run(main())
