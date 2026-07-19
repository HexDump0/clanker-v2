"""Command-line entry points.

    clanker queue             one-shot look at the pending queue
    clanker show <cert-id>    full detail for one cert
    clanker watch             run the watcher only (logs new certs, no reviews)
    clanker review <cert-id>  run one full review (verdict + PDF, no Slack)
    clanker run               run everything: watcher + reviews + Slack
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from clanker.config import Settings, load_settings
from clanker.shipwrights import CertStatus, CertSummary, ShipwrightsClient
from clanker.watcher import Watcher


def _describe(cert: CertSummary) -> str:
    return (
        f"{cert.id}  {cert.project_name!r} "
        f"[{cert.project_type or cert.ai_type or '?'}] "
        f"by {cert.submitter_username or cert.submitter_slack_id or '?'} "
        f"(dev time {cert.dev_time or '?'})"
    )


async def cmd_queue(settings: Settings, args: argparse.Namespace) -> None:
    async with ShipwrightsClient.from_settings(settings) as sw:
        page = await sw.list_certifications(status=CertStatus(args.status), page=args.page)
    print(f"{page.total} certs ({args.status}), page {page.page}/{page.pages}")
    if page.stats:
        print("stats:", ", ".join(f"{k}={v}" for k, v in sorted(page.stats.items())))
    for cert in page.certs:
        print(" ", _describe(cert))


async def cmd_show(settings: Settings, args: argparse.Namespace) -> None:
    async with ShipwrightsClient.from_settings(settings) as sw:
        detail = await sw.get_certification(args.cert_id)
    print(detail.model_dump_json(indent=2, by_alias=True))


async def cmd_watch(settings: Settings, args: argparse.Namespace) -> None:
    async with ShipwrightsClient.from_settings(settings) as sw:
        watcher = Watcher(
            sw,
            state_file=settings.watcher_state_file,
            poll_interval=args.interval or settings.watcher_poll_interval,
            emit_backlog=settings.watcher_emit_backlog,
        )

        async def announce(cert: CertSummary) -> None:
            print("NEW:", _describe(cert))

        await watcher.run(announce)


async def cmd_review(settings: Settings, args: argparse.Namespace) -> None:
    from clanker.config import configure_observability
    from clanker.service import build_app

    configure_observability(settings)
    ctx = build_app(settings, with_slack=False)
    try:
        outcome = await ctx.runner.review_cert(args.cert_id)
    finally:
        await ctx.client.close()
        await ctx.tools.aclose()

    review = outcome.review
    print(f"\nVerdict: {review.verdict.value}  ({review.project_type})")
    print(f"Reasoning: {review.reasoning}")
    if review.required_fixes:
        print("Required fixes:")
        for fix in review.required_fixes:
            print(f"  - {fix}")
    if review.special_flags:
        print(f"Flags: {', '.join(review.special_flags)}")
    print("Checks:")
    for row in review.checks.as_pdf_rows():
        print(f"  [{row['status']:>4}] {row['name']}: {row['details']}")
    print(f"\nPDF: {outcome.pdf_path or '(generation failed)'}")
    print(f"Tokens: {outcome.input_tokens} in / {outcome.output_tokens} out")


async def cmd_run(settings: Settings, args: argparse.Namespace) -> None:
    from clanker.service import run_all

    await run_all(settings)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="clanker", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_queue = sub.add_parser("queue", help="list certifications")
    p_queue.add_argument("--status", default="PENDING", choices=[s.value for s in CertStatus])
    p_queue.add_argument("--page", type=int, default=1)
    p_queue.set_defaults(func=cmd_queue)

    p_show = sub.add_parser("show", help="show one certification")
    p_show.add_argument("cert_id")
    p_show.set_defaults(func=cmd_show)

    p_watch = sub.add_parser("watch", help="watch for new pending certs")
    p_watch.add_argument("--interval", type=float, default=None, help="poll interval seconds")
    p_watch.set_defaults(func=cmd_watch)

    p_review = sub.add_parser("review", help="run one full review (no Slack)")
    p_review.add_argument("cert_id")
    p_review.set_defaults(func=cmd_review)

    p_run = sub.add_parser("run", help="run all services (watcher + reviews + Slack)")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    try:
        asyncio.run(args.func(settings, args))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
