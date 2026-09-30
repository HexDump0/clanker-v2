"""Export frozen production review traces from Logfire.

Each row keeps exactly what the production review agent saw (packet + tool results) and
what DeepSeek decided, so Jev can be replayed on identical evidence with no repo drift.

Needs LOGFIRE_READ_TOKEN (a *read* token for floppy/clanker-v2) in the env or .env.

    uv run python evals/jev/export_traces.py --per-verdict 60
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import UTC, datetime, timedelta

from dotenv import dotenv_values
from logfire.query_client import AsyncLogfireQueryClient

from common import DATA, REVIEW_MARKER, TRACES

CERT_RE = re.compile(r"cert id: ([0-9a-f-]{36})")

LIST_SQL = f"""
SELECT trace_id, start_timestamp, duration,
       attributes->'final_result'->>'verdict' AS verdict,
       (attributes->>'gen_ai.aggregated_usage.input_tokens')::bigint AS input_tokens,
       (attributes->>'gen_ai.aggregated_usage.output_tokens')::bigint AS output_tokens,
       (attributes->>'gen_ai.aggregated_usage.cache_read.input_tokens')::bigint AS cache_tokens
FROM records
WHERE span_name = 'invoke_agent agent'
  AND attributes->>'gen_ai.system_instructions' LIKE '%{REVIEW_MARKER}%'
  AND otel_status_code IS DISTINCT FROM 'ERROR'
"""

DETAIL_SQL = """
SELECT trace_id, attributes->>'pydantic_ai.all_messages' AS messages,
       attributes->>'final_result' AS final_result
FROM records
WHERE span_name = 'invoke_agent agent' AND trace_id = '{trace_id}'
  AND attributes->>'gen_ai.system_instructions' LIKE '%Shipwright Reviewer Agent%'
"""


async def _query(client: AsyncLogfireQueryClient, sql: str, **kwargs) -> dict:
    """query_json_rows with backoff: the read API rate-limits per minute."""
    for attempt in range(8):
        try:
            return await client.query_json_rows(sql, **kwargs)
        except AssertionError as exc:
            if "Rate limit" not in str(exc):
                raise
            wait = min(60, 5 * 2**attempt)
            print(f"  rate limited, sleeping {wait}s")
            await asyncio.sleep(wait)
    raise RuntimeError("Logfire rate limit persisted")


def _json(value):
    """Logfire returns JSON attributes as text, already-parsed values, or empty strings."""
    if isinstance(value, str):
        try:
            return json.loads(value) if value.strip() else None
        except json.JSONDecodeError:
            return value
    return value


def _token() -> str:
    token = os.environ.get("LOGFIRE_READ_TOKEN") or dotenv_values(".env").get(
        "LOGFIRE_READ_TOKEN"
    )
    if not token:
        raise SystemExit("LOGFIRE_READ_TOKEN is not set")
    return token


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-09-12")
    parser.add_argument("--end", default="2026-09-25")
    parser.add_argument("--per-verdict", type=int, default=60)
    parser.add_argument(
        "--random", type=int, default=0,
        help="uniform seeded sample of N reviews (production verdict mix) instead of stratifying",
    )
    args = parser.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)
    done = set()
    if TRACES.exists():
        done = {json.loads(line)["trace_id"] for line in TRACES.open() if line.strip()}

    start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    end = datetime.fromisoformat(args.end).replace(tzinfo=UTC)
    async with AsyncLogfireQueryClient(read_token=_token()) as client:
        # Query day by day to stay under the per-query scan budget.
        cache = DATA / f"candidates_{args.start}_{args.end}.json"
        if cache.exists():
            candidates = json.loads(cache.read_text())
        else:
            candidates = []
            day = start
            while day < end:
                nxt = min(day + timedelta(days=1), end)
                rows = await _query(client, LIST_SQL, min_timestamp=day, max_timestamp=nxt)
                candidates += rows["rows"]
                day = nxt
            cache.write_text(json.dumps(candidates))

        # Deterministic stratified sample: every k-th run per DeepSeek verdict, spread over
        # the whole window so no single day dominates.
        if args.random:
            import random

            picked = random.Random(1234).sample(candidates, min(args.random, len(candidates)))
            print(f"{len(candidates)} candidates, random sample {len(picked)}")
        by_verdict: dict[str, list[dict]] = {}
        for row in sorted(candidates, key=lambda r: r["start_timestamp"]):
            by_verdict.setdefault(row["verdict"] or "?", []).append(row)
        if not args.random:
            picked = []
        for verdict, rows in ([] if args.random else by_verdict.items()):
            step = max(1, len(rows) // args.per_verdict)
            picked += rows[::step][: args.per_verdict]
            print(f"{verdict}: {len(rows)} candidates, picked {min(len(rows[::step]), args.per_verdict)}")

        for i, row in enumerate(picked):
            if row["trace_id"] in done:
                continue
            ts = datetime.fromisoformat(row["start_timestamp"].replace("Z", "+00:00"))
            detail = await _query(
                client,
                DETAIL_SQL.format(trace_id=row["trace_id"]),
                min_timestamp=ts - timedelta(minutes=1),
                max_timestamp=ts + timedelta(hours=1),
            )
            if not detail["rows"]:
                continue
            d = detail["rows"][0]
            messages = _json(d["messages"])
            if not isinstance(messages, list) or not messages:
                continue
            first = messages[0]["parts"][0]["content"]
            match = CERT_RE.search(first)
            out = {
                **row,
                "cert_id": match.group(1) if match else None,
                "final_result": _json(d["final_result"]),
                "messages": messages,
            }
            with TRACES.open("a", encoding="utf-8") as f:
                f.write(json.dumps(out, ensure_ascii=False) + "\n")
            print(f"[{i + 1}/{len(picked)}] {out['cert_id']} {row['verdict']}")


if __name__ == "__main__":
    asyncio.run(main())
