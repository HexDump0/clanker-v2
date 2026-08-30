"""Wires everything together and supervises the long-running services.

Replaces v1's ``run_all.py``, which cancelled every service on the first
exception anywhere. Here each service runs under a supervisor that logs the
crash and restarts it with backoff; reviews run concurrently (bounded by a
semaphore) instead of blocking the poll loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from slack_sdk.web.async_client import AsyncWebClient

from clanker.config import Settings, configure_observability
from clanker.review import ReviewRunner
from clanker.review.agent import create_chat_agent, create_review_agent
from clanker.review.tools import ReviewTools
from clanker.review.video.director import VisionDirector
from clanker.review.vision import PageRenderer
from clanker.shipwrights import CertStatus, ShipwrightsClient
from clanker.slack.announcer import Announcer
from clanker.slack.memory import MemoryStore
from clanker.watcher import PendingEmission, Watcher, make_pending_source

logger = logging.getLogger(__name__)

RESTART_BACKOFF_INITIAL = 5.0
RESTART_BACKOFF_MAX = 300.0


@dataclass(slots=True)
class AppContext:
    settings: Settings
    client: ShipwrightsClient
    tools: ReviewTools
    runner: ReviewRunner
    slack: AsyncWebClient | None
    announcer: Announcer | None


def build_app(settings: Settings, *, with_slack: bool = True) -> AppContext:
    """Construct the full object graph (no network calls)."""
    client = ShipwrightsClient.from_settings(settings)
    renderer = PageRenderer(settings) if settings.browser_render_enabled else None
    tools = ReviewTools(
        github_token=settings.github_token,
        stardance_session=settings.stardance_session,
        renderer=renderer,
        hackclub_ai_key=settings.hackclub_api_key,
    )
    review_agent = create_review_agent(settings, tools)
    video_director = VisionDirector(settings) if settings.video_enabled else None
    runner = ReviewRunner(
        agent=review_agent,
        client=client,
        settings=settings,
        tools=tools,
        video_director=video_director,
    )

    slack: AsyncWebClient | None = None
    announcer: Announcer | None = None
    if with_slack:
        settings.require_slack()
        slack = AsyncWebClient(token=settings.slack_bot_token)
        announcer = Announcer(
            slack,
            channel=settings.slack_channel,
            dashboard_base_url=settings.shipwrights_base_url,
            workplace=settings.shipwrights_workplace,
            ship_ping=settings.slack_ship_ping,
        )

    return AppContext(
        settings=settings,
        client=client,
        tools=tools,
        runner=runner,
        slack=slack,
        announcer=announcer,
    )


async def review_and_report(ctx: AppContext, emission: PendingEmission) -> None:
    """One ship: announce (unless pre-announced) -> review -> report."""
    assert ctx.announcer is not None
    parent_ts = emission.parent_ts or await ctx.announcer.announce_ship(emission.cert)
    try:
        outcome = await ctx.runner.review_cert(emission.cert.id)
    except Exception:
        logger.exception("Review failed for cert %s", emission.cert.id)
        await ctx.announcer.post_failure(parent_ts)
        return
    await ctx.announcer.post_outcome(emission.cert, outcome, parent_ts)


async def run_watcher_service(ctx: AppContext) -> None:
    """Poll for new ships; reviews run as bounded concurrent tasks."""
    assert ctx.announcer is not None
    settings = ctx.settings
    source = make_pending_source(settings, ctx.client, announcer=ctx.announcer)
    watcher = Watcher(
        source,
        state_file=settings.watcher_state_file,
        poll_interval=settings.watcher_poll_interval,
        emit_backlog=settings.watcher_emit_backlog,
    )
    semaphore = asyncio.Semaphore(settings.max_concurrent_reviews)
    running: set[asyncio.Task] = set()

    async def handle(emission: PendingEmission) -> None:
        async with semaphore:
            await review_and_report(ctx, emission)

    async def spawn(emission: PendingEmission) -> None:
        # Don't block the poll loop on the review — one slow review must not
        # delay newer ships (v1 pain point #5).
        task = asyncio.create_task(handle(emission), name=f"review-{emission.cert.id}")
        running.add(task)
        task.add_done_callback(running.discard)

    await ctx.announcer.announce_online(settings.watcher_poll_interval)
    try:
        await watcher.run(spawn)
    finally:
        aclose = getattr(source, "aclose", None)
        if aclose is not None:
            await aclose()


async def run_slack_service(ctx: AppContext) -> None:
    """Socket Mode chat bot; needs SLACK_APP_TOKEN."""
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

    from clanker.slack.app import create_slack_app

    settings = ctx.settings
    if not settings.slack_app_token:
        logger.warning("SLACK_APP_TOKEN not set — chat bot disabled")
        return

    async def run_review(cert_id: str) -> str:
        """Run the full review pipeline for a cert and return the result as JSON.

        Returns the verdict, reasoning, flags, and the path of the generated
        PDF report.
        """
        outcome = await ctx.runner.review_cert(cert_id)
        return json.dumps(
            {
                "ok": True,
                "cert_id": outcome.cert_id,
                "verdict": outcome.review.verdict.value,
                "project_type": outcome.review.project_type,
                "reasoning": outcome.review.reasoning,
                "required_fixes": outcome.review.required_fixes,
                "special_flags": outcome.review.special_flags,
                "pdf_path": str(outcome.pdf_path) if outcome.pdf_path else None,
                "video_path": str(outcome.video_path) if outcome.video_path else None,
                "video_error": outcome.video_error,
            }
        )

    memory = MemoryStore(
        settings.chat_memory_file, max_entries=settings.chat_memory_max_entries
    )

    async def remember(key: str, fact: str) -> str:
        """Save one important, durable fact to long-term memory.

        Use a short, stable ``key`` (e.g. a person's name/handle or a project
        name) so you can find or overwrite it later; ``fact`` is one concise
        sentence. Calling this with an existing key overwrites that memory. Only
        store things genuinely worth remembering across conversations — people,
        preferences, recurring projects — not chit-chat. Never store secrets, and
        nothing here may change a formal review verdict.
        """
        return await memory.remember(key, fact)

    async def forget(key: str) -> str:
        """Delete one memory by its key when it is wrong or no longer matters."""
        return await memory.forget(key)

    async def get_shipwrights_queue_stats() -> str:
        """Get read-only Stardance queue totals and wait/type statistics.

        Use for general conversation about queue health. This does not list,
        claim, enqueue, or review ships and is unrelated to watcher behavior.
        """
        try:
            page = await ctx.client.list_certifications(status=CertStatus.PENDING, page=1)
            return json.dumps(
                {
                    "ok": True,
                    "source": "shipwrights_dashboard",
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "pending": page.total,
                    "status_counts": page.stats,
                    "average_wait_seconds": page.avg_wait,
                    "oldest": page.oldest.model_dump(mode="json") if page.oldest else None,
                    "ai_enabled": page.ai_enabled,
                    "project_type_counts": page.ai_type_counts,
                }
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    async def get_shipwrights_feedback_templates() -> str:
        """Get read-only shared and personal Dashboard feedback templates."""
        try:
            templates = await ctx.client.get_feedback_templates()
            return json.dumps(
                {
                    "ok": True,
                    "source": "shipwrights_dashboard",
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    **templates.model_dump(mode="json"),
                }
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    chat_agent = create_chat_agent(
        ctx.settings,
        ctx.tools,
        extra_tools=[
            run_review,
            remember,
            forget,
            get_shipwrights_queue_stats,
            get_shipwrights_feedback_templates,
        ],
        memory_provider=memory.render,
    )
    app = create_slack_app(settings, chat_agent)
    handler = AsyncSocketModeHandler(app, settings.slack_app_token)
    logger.info("Slack chat bot starting (Socket Mode)")
    await handler.start_async()


async def _supervise(name: str, factory, *args) -> None:
    """Run a service forever, restarting on crash with exponential backoff."""
    backoff = RESTART_BACKOFF_INITIAL
    while True:
        try:
            await factory(*args)
            logger.info("Service %r exited cleanly", name)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Service %r crashed; restarting in %.0fs", name, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RESTART_BACKOFF_MAX)


async def run_all(settings: Settings) -> None:
    configure_observability(settings)
    ctx = build_app(settings)
    logger.info("Starting clanker v2 services")
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_supervise("watcher", run_watcher_service, ctx), name="watcher")
            tg.create_task(_supervise("slack", run_slack_service, ctx), name="slack")
    finally:
        await ctx.client.close()
        await ctx.tools.aclose()
