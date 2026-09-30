"""Replay frozen traces through Jev (via OpenRouter) for both arms.

    uv run --with typesafe-sdk==0.7.2 python evals/jev/run_jev.py --dry-run
    uv run --with typesafe-sdk==0.7.2 python evals/jev/run_jev.py --budget 0.30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

from common import (
    CODE,
    DATA,
    JEV_MODEL,
    OPENROUTER_TYPESAFE_BASE,
    RESULTS,
    TRACES,
    append_jsonl,
    read_jsonl,
)
from questions import build_questions, rule_verdict
from questions_reject import build_reject_questions
from state import build_states
from typesafe_sdk import AsyncTypeSafeClient

from clanker.config import load_settings

PRICE_PER_TOKEN = 0.042 / 1_000_000


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms", default="packet,bunny", help="packet, bunny, agent (DeepSeek tools), reject (first-layer confident-reject set)")
    parser.add_argument("--budget", type=float, default=0.30, help="USD cap for this run")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    arms = args.arms.split(",")
    done = {(r["trace_id"], r["arm"]) for r in read_jsonl(RESULTS) if "error" not in r}
    traces = list(read_jsonl(TRACES))
    if args.limit:
        traces = traces[: args.limit]

    bunny = {b["trace_id"]: b for b in read_jsonl(DATA / "bunny.jsonl") if "error" not in b}
    code = {c["trace_id"]: c for c in read_jsonl(CODE)}
    ev2 = {e["trace_id"]: e for e in read_jsonl(DATA / "evidence2.jsonl")}
    jobs = []
    for t in traces:
        states = build_states(t, bunny.get(t["trace_id"]), code.get(t["trace_id"]), ev2.get(t["trace_id"]))
        for arm in arms:
            if arm in states and (t["trace_id"], arm) not in done:
                jobs.append((t, arm, states))

    if args.dry_run:
        sizes = [len(json.dumps(s[a], ensure_ascii=False)) for _, a, s in jobs]
        est_tokens = sum(sizes) / 3.2 + len(jobs) * 3_000
        print(f"{len(jobs)} jobs · state chars avg {sum(sizes) / max(1, len(sizes)):.0f} "
              f"max {max(sizes, default=0)} · est cost ${est_tokens * PRICE_PER_TOKEN:.3f}")
        return

    settings = load_settings()
    spent = 0.0
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(args.concurrency)

    async with AsyncTypeSafeClient(
        api_key=settings.openrouter_api_key, base_url=OPENROUTER_TYPESAFE_BASE, model=JEV_MODEL,
        timeout=60,
    ) as client:

        async def run(trace: dict, arm: str, states: dict) -> None:
            nonlocal spent
            async with sem:
                async with lock:
                    if spent >= args.budget:
                        return
                started = time.perf_counter()
                row = {"trace_id": trace["trace_id"], "cert_id": trace["cert_id"], "arm": arm}
                try:
                    questions = (
                        build_reject_questions()
                        if arm in ("reject", "reject2")
                        else build_questions(with_investigation=arm != "packet")
                    )
                    resp = await client.system_one(states[arm], questions)
                except Exception as exc:
                    append_jsonl(RESULTS, {**row, "error": f"{type(exc).__name__}: {exc}"})
                    print("ERR", trace["cert_id"], arm, exc)
                    return
                data = resp.model_dump()
                answers = data["answers"]
                verdict, reasons = (
                    ("n/a", []) if arm.startswith("reject") else rule_verdict(answers, states["facts"])
                )
                usage = data.get("usage") or {}
                async with lock:
                    spent += (usage.get("input_tokens") or 0) * PRICE_PER_TOKEN
                append_jsonl(
                    RESULTS,
                    {
                        **row,
                        "model": data.get("model"),
                        "latency_s": round(time.perf_counter() - started, 3),
                        "usage": usage,
                        "answers": answers,
                        "rule_verdict": verdict,
                        "rule_reasons": reasons,
                        "facts": states["facts"],
                    },
                )

        await asyncio.gather(*(run(t, a, s) for t, a, s in jobs))
    print(f"done · approx spend ${spent:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
