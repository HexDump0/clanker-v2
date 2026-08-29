"""Benchmark clanker-v2 review accuracy against human decisions.

Reads a CSV of already-reviewed certs (ground truth), runs the real review
agent on each with the ground-truth verdict *stripped from the packet*, and
records the full ``ReviewOutput`` per cert to a JSONL for scoring.

Ground truth (CSV):
  - id          Stardance ship id == the cert's ``external_id`` (NOT the
                Shipwrights cert id, which is a UUID resolved via search).
  - status      1 -> human APPROVED, 2 -> human REJECTED.

Leak neutralization (these certs are already decided, so the verdict is
present in two places the agent would otherwise see):
  1. ``packet.cert.reviews`` — the prior-review section prints the human's
     exact verdict + comment. Cleared before rendering the prompt.
  2. The Stardance admin ship page (``/admin/certification/ship/{id}``) is an
     admin view that can render the decision. The packet's stardance section is
     dropped AND ``fetch_stardance_project`` is removed from the agent toolset,
     so neither the packet nor an agent tool call can reach it.

No mutating API calls are ever made (read-only session usage only). PDF and
video generation are skipped for speed.

Usage:
  uv run python scripts/bench_reviews.py --limit 25          # pilot
  uv run python scripts/bench_reviews.py                     # full run (resumes)
  uv run python scripts/bench_reviews.py --concurrency 6 --out data/bench/results.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace

import logfire
from pydantic_ai import Agent, PromptedOutput
from slack_sdk.http_retry.builtin_async_handlers import AsyncRateLimitErrorRetryHandler
from slack_sdk.web.async_client import AsyncWebClient

from clanker.config import Settings, configure_observability, load_settings
from clanker.llm import build_model
from clanker.review.agent import build_model_settings, build_review_instructions
from clanker.review.models import ReviewOutput, ReviewVerdict
from clanker.review.packet import build_packet
from clanker.review.tools import ReviewTools
from clanker.review.vision import PageRenderer
from clanker.shipwrights import ShipwrightsClient
from clanker.slack.announcer import Announcer

logger = logging.getLogger("bench")

CSV_PATH = Path("data/bench/500-recently-reviewed-certs.csv")
DEFAULT_OUT = Path("data/bench/results.jsonl")

# CSV status -> the human ground-truth verdict, in the agent's vocabulary.
TRUTH = {"1": "APPROVE", "2": "REJECT"}


def build_benchmark_agent(settings: Settings, tools: ReviewTools) -> Agent[None, ReviewOutput]:
    """The real review agent, but with the Stardance admin-page tool removed so
    it cannot pull the decided cert's verdict from the admin view."""
    safe_tools = [t for t in tools.all() if t.__name__ != "fetch_stardance_project"]
    return Agent(
        build_model(settings),
        output_type=PromptedOutput(ReviewOutput),
        instructions=build_review_instructions(),
        model_settings=build_model_settings(settings),
        tools=safe_tools,
        retries=4,
    )


async def resolve_cert_id(sw: ShipwrightsClient, external_id: str) -> str | None:
    """Map a Stardance ship id (CSV ``id``) to the Shipwrights cert UUID."""
    page = 1
    while page <= 3:
        result = await sw.list_certifications(query=external_id, page=page)
        for cert in result.certs:
            if cert.external_id == external_id:
                return cert.id
        if page >= result.pages or not result.certs:
            break
        page += 1
    return None


_VERDICT_LABEL = {
    ReviewVerdict.APPROVE: "APPROVE",
    ReviewVerdict.REJECT: "REJECT",
    ReviewVerdict.FLAG_FOR_HUMAN: "NEEDS HUMAN",
}


async def review_one(
    row: dict[str, str],
    sw: ShipwrightsClient,
    tools: ReviewTools,
    agent: Agent[None, ReviewOutput],
    announcer: Announcer | None,
) -> dict:
    external_id = row["id"]
    truth = TRUTH.get(row["status"])
    record: dict = {
        "id": external_id,
        "project_id": row.get("project_id"),
        "truth": truth,
        "csv_status": row["status"],
    }
    started = time.perf_counter()
    # A benchmark-tagged span so these runs are filterable in Logfire and never
    # mistaken for a production review.
    with logfire.span(
        "bench_review",
        cert_external_id=external_id,
        truth=truth,
        benchmark=True,
    ) as span:
        parent_ts: str | None = None
        cert = None
        try:
            cert_uuid = await resolve_cert_id(sw, external_id)
            if cert_uuid is None:
                record["error"] = "could not resolve external_id to a cert UUID"
                return record
            record["cert_uuid"] = cert_uuid
            span.set_attribute("cert_uuid", cert_uuid)

            packet = await build_packet(sw, cert_uuid, tools=tools)
            # --- leak neutralization ---
            packet.cert.reviews = []      # prior human verdict + comment
            packet.stardance = None       # admin ship page (may render the decision)

            cert = packet.cert
            record["project_name"] = cert.project_name

            # Announce the ship to Slack exactly as production does (minus the ping).
            if announcer is not None:
                parent_ts = await announcer.announce_ship(cert)

            result = await agent.run(packet.to_prompt())
            review = result.output
            usage = result.usage

            record["predicted"] = review.verdict.value
            record["review"] = review.model_dump(mode="json")  # full output, for completeness
            record["input_tokens"] = usage.input_tokens
            record["output_tokens"] = usage.output_tokens
            record["requests"] = usage.requests
            span.set_attribute("predicted", review.verdict.value)

            # Update the ship embed with the verdict (no PDF/video artifacts).
            if announcer is not None and parent_ts is not None:
                await _post_verdict(announcer, cert, review, parent_ts)
        except Exception as exc:  # keep the run going; one bad cert isn't fatal
            logger.exception("Review failed for cert %s", external_id)
            record["error"] = f"{type(exc).__name__}: {exc}"
            span.set_attribute("error", record["error"])
            if announcer is not None and parent_ts is not None:
                await announcer.post_failure(parent_ts)
        finally:
            record["elapsed_s"] = round(time.perf_counter() - started, 1)
    return record


async def _post_verdict(
    announcer: Announcer, cert, review: ReviewOutput, parent_ts: str
) -> None:
    """Update the ship embed with the verdict only (no PDF/video upload)."""
    label = _VERDICT_LABEL.get(review.verdict, "NEEDS HUMAN")
    outcome_stub = SimpleNamespace(review=review)
    try:
        await announcer._slack.chat_update(
            channel=announcer._channel,
            ts=parent_ts,
            attachments=[
                announcer._ship_attachment(
                    cert,
                    status_label=label,
                    verdict_block=announcer._verdict_block(outcome_stub),
                )
            ],
        )
    except Exception:
        logger.exception("Failed to update Slack embed with verdict")


def load_done(out_path: Path) -> set[str]:
    """External ids already written (successfully) — for resuming."""
    if not out_path.exists():
        return set()
    done: set[str] = set()
    with out_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Only treat as done if it produced a prediction or a hard resolve
            # failure; transient errors are retried on the next run.
            if rec.get("predicted") or rec.get("error", "").startswith("could not resolve"):
                done.add(str(rec.get("id")))
    return done


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=None, help="cap number of certs (pilot)")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--no-resume", action="store_true", help="ignore existing results")
    parser.add_argument(
        "--slack",
        action="store_true",
        help="post ship announcements + verdicts to SLACK_CHANNEL (no ping, no PDF)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = load_settings()
    configure_observability(settings)

    with args.csv.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    done = set() if args.no_resume else load_done(args.out)
    todo = [r for r in rows if str(r["id"]) not in done]
    if args.limit is not None:
        todo = todo[: args.limit]

    print(
        f"Model: {settings.model_name} | provider: {settings.ai_provider}\n"
        f"CSV rows: {len(rows)} | already done: {len(done)} | this run: {len(todo)} "
        f"| concurrency: {args.concurrency}"
    )
    if not todo:
        print("Nothing to do.")
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)

    renderer = PageRenderer(settings) if settings.browser_render_enabled else None
    tools = ReviewTools(
        github_token=settings.github_token,
        stardance_session=settings.stardance_session,
        renderer=renderer,
        hackclub_ai_key=settings.hackclub_api_key,
    )
    agent = build_benchmark_agent(settings, tools)

    announcer: Announcer | None = None
    if args.slack:
        settings.require_slack()
        slack = AsyncWebClient(
            token=settings.slack_bot_token,
            retry_handlers=[AsyncRateLimitErrorRetryHandler(max_retry_count=3)],
        )
        # Force the cc ship-ping OFF for the benchmark — 500 group pings is never right.
        announcer = Announcer(
            slack,
            channel=settings.slack_channel,
            dashboard_base_url=settings.shipwrights_base_url,
            workplace=settings.shipwrights_workplace,
            ship_ping="",
        )
        print(f"Slack: posting to channel {settings.slack_channel} (no ping, no PDF)")

    sem = asyncio.Semaphore(args.concurrency)
    write_lock = asyncio.Lock()
    counter = {"done": 0}
    out_fh = args.out.open("a", encoding="utf-8")

    async with ShipwrightsClient.from_settings(settings) as sw:

        async def worker(row: dict[str, str]) -> None:
            async with sem:
                rec = await review_one(row, sw, tools, agent, announcer)
            async with write_lock:
                out_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out_fh.flush()
                counter["done"] += 1
                mark = rec.get("predicted") or rec.get("error", "?")[:30]
                print(
                    f"[{counter['done']}/{len(todo)}] {rec['id']} "
                    f"truth={rec.get('truth')} -> {mark} ({rec.get('elapsed_s')}s)"
                )

        try:
            await asyncio.gather(*(worker(r) for r in todo))
        finally:
            out_fh.close()
            await tools.aclose()

    print(f"\nDone. Results in {args.out}. Score with: uv run python scripts/score_bench.py")


if __name__ == "__main__":
    asyncio.run(main())
