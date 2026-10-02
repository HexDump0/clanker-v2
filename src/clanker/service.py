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
from typing import TYPE_CHECKING

from slack_sdk.web.async_client import AsyncWebClient

from clanker.config import Settings, configure_observability
from clanker.daily import parse_daily_time, seconds_until_utc_time, send_daily_summary
from clanker.review import ReviewRunner
from clanker.review.agent import create_chat_agent, create_review_agent
from clanker.review.first_layer import FirstLayerReviewer
from clanker.review.tools import ReviewTools
from clanker.review.video.director import VisionDirector
from clanker.review.vision import PageRenderer
from clanker.shipwrights import CertStatus, ShipwrightsClient
from clanker.slack.announcer import Announcer
from clanker.slack.memory import MemoryStore
from clanker.watcher import PendingEmission, Watcher, make_pending_source

if TYPE_CHECKING:
    from clanker.results import ResultStore
    from clanker.status import StatusRefresher

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
    if settings.review_mode == "first_layer":
        # Code checks + one Jev call; reject videos are code-directed (no director model).
        runner = ReviewRunner(
            first_layer=FirstLayerReviewer(settings),
            client=client,
            settings=settings,
            tools=tools,
        )
    else:
        runner = ReviewRunner(
            agent=create_review_agent(settings, tools),
            client=client,
            settings=settings,
            tools=tools,
            video_director=VisionDirector(settings) if settings.video_enabled else None,
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
            daily_ping=settings.slack_daily_ping,
            reject_ping=settings.slack_reject_ping,
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
    _remember_thread(ctx, emission.cert.id, parent_ts)
    await ctx.announcer.post_outcome(emission.cert, outcome, parent_ts)


def _remember_thread(ctx: AppContext, cert_id: str, parent_ts: str) -> None:
    """Keep the Slack thread with the result so a later "wrong" flag lands in it."""
    from clanker.results import ResultStore

    try:
        ResultStore(ctx.settings.results_dir).set_slack_ts(cert_id, parent_ts)
    except Exception:
        logger.exception("Could not remember the Slack thread for cert %s", cert_id)


async def flag_manual_review(ctx: AppContext, record) -> None:
    """Tell Slack a human marked Clanker's review wrong (no-op without Slack)."""
    if ctx.announcer is None:
        return
    fb = record.feedback
    labels = dict(zip(record.reasons, record.reason_labels, strict=False))
    await ctx.announcer.post_manual_review(
        record.cert_id,
        record.project_name,
        parent_ts=record.slack_ts,
        note=fb.note if fb else "",
        wrong_reasons=[labels.get(c, c) for c in (fb.wrong_checks if fb else [])],
        by=fb.by_name if fb else None,
    )


async def review_for_extension(
    ctx: AppContext, cert_id: str, requested_by: str | None = None
) -> None:
    """A review requested from the browser extension: Slack updates, then the review itself.

    Slack trouble never blocks the review; a failed review is re-raised so the extension
    sees the error.
    """
    from clanker.results import ResultStore

    rereview = ResultStore(ctx.settings.results_dir).get(cert_id) is not None
    cert = None
    parent_ts: str | None = None
    if ctx.announcer is not None:
        try:
            cert = await ctx.client.get_certification(cert_id)
            parent_ts = await ctx.announcer.announce_review_request(
                cert, rereview=rereview, requested_by=requested_by
            )
        except Exception:
            logger.exception("Could not announce extension review for cert %s", cert_id)
    try:
        outcome = await ctx.runner.review_cert(cert_id)
    except Exception:
        if parent_ts is not None and ctx.announcer is not None:
            await ctx.announcer.post_failure(parent_ts)
        raise
    if requested_by:
        ResultStore(ctx.settings.results_dir).set_requested_by(cert_id, requested_by)
    if parent_ts is not None:
        _remember_thread(ctx, cert_id, parent_ts)
    if parent_ts is not None and cert is not None and ctx.announcer is not None:
        try:
            await ctx.announcer.post_outcome(cert, outcome, parent_ts)
        except Exception:
            logger.exception("Could not post extension review outcome for cert %s", cert_id)


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


async def run_daily_summary_service(ctx: AppContext) -> None:
    """Post the daily queue summary once per day at DAILY_SUMMARY_TIME_UTC."""
    assert ctx.announcer is not None
    settings = ctx.settings
    hour, minute = parse_daily_time(settings.daily_summary_time_utc)
    while True:
        delay = seconds_until_utc_time(hour, minute)
        logger.info("Daily queue summary next post in %.0f s (%02d:%02d UTC)", delay, hour, minute)
        await asyncio.sleep(delay)
        try:
            await send_daily_summary(ctx.client, ctx.announcer, settings)
        except Exception:
            # One failed digest must not kill the schedule; the supervisor
            # restarts us anyway, but log loudly either way.
            logger.exception("Daily queue summary failed")


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

        Returns the verdict, reasoning, flags, the ready-to-send reject message
        (first-layer rejects only), and the path of the generated PDF report.
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
                "reject_message": outcome.reject_message,
                "pdf_path": str(outcome.pdf_path) if outcome.pdf_path else None,
                "video_path": str(outcome.video_path) if outcome.video_path else None,
                "video_error": outcome.video_error,
            }
        )

    memory = MemoryStore(settings.chat_memory_file, max_entries=settings.chat_memory_max_entries)

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
    refreshers: list[StatusRefresher] = []
    logger.info("Starting clanker v2 services")
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_supervise("watcher", run_watcher_service, ctx), name="watcher")
            tg.create_task(_supervise("slack", run_slack_service, ctx), name="slack")
            if settings.extension_api_enabled:
                from clanker.api import run_extension_api
                from clanker.results import ResultStore

                store = ResultStore(settings.results_dir)
                refresher = _build_refresher(settings, store)
                if refresher is not None:
                    refreshers.append(refresher)
                    tg.create_task(
                        run_status_service(refresher, sweep=settings.status_startup_sweep),
                        name="status",
                    )
                tg.create_task(
                    _supervise(
                        "extension-api",
                        run_extension_api,
                        settings,
                        store,
                        lambda cert_id, who: review_for_extension(ctx, cert_id, who),
                        lambda record: flag_manual_review(ctx, record),
                        refresher.maybe_refresh if refresher else None,
                    ),
                    name="extension-api",
                )
            if settings.daily_summary_enabled:
                tg.create_task(
                    _supervise("daily-summary", run_daily_summary_service, ctx),
                    name="daily-summary",
                )
    finally:
        await ctx.client.close()
        await ctx.tools.aclose()
        for refresher in refreshers:
            await refresher.aclose()


def _build_refresher(settings: Settings, store: ResultStore) -> StatusRefresher | None:
    """The ship-state refresher, when it has what it needs: a Stardance session.

    Returns None (and says why) rather than silently serving a queue that can never tell a
    decided ship from a waiting one.
    """
    from clanker.stardance import StardanceAdminClient
    from clanker.status import ReviewLogCache, StatusRefresher

    if not settings.status_refresh_enabled:
        return None
    if not settings.stardance_session:
        logger.warning(
            "STATUS_REFRESH_ENABLED is on but STARDANCE_SESSION is not set, so the Clanker "
            "queue cannot tell which ships a human has already reviewed"
        )
        return None
    cache = ReviewLogCache(settings.status_cache_file)
    cache.load()
    return StatusRefresher(
        StardanceAdminClient(settings.stardance_session),
        store,
        cache=cache,
        interval=settings.status_refresh_interval,
        log_limit=settings.status_refresh_log_limit,
        cache_max_pages=settings.status_cache_max_pages,
        cache_interval=settings.status_cache_interval,
        startup_pages=settings.status_startup_pages,
        backfill_limit=settings.status_refresh_backfill,
    )


async def run_status_service(refresher: StatusRefresher, *, sweep: bool = True) -> None:
    """Keep the Clanker queue correct in the background.

    Ships get approved and returned while nobody is looking at the extension, and while the bot
    is down entirely, so the queue cannot be left to whoever opens the page next. This sweeps
    once at boot — a restart must not leave decided ships sitting in the queue — and then
    reconciles on a timer.
    """
    if sweep:
        try:
            await refresher.startup_sweep()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Startup sweep failed; the queue catches up on the next pass")
    logger.info(
        "Background reconciliation every %.0f s (on-demand passes every %.0f s)",
        refresher.cache_interval,
        refresher.interval,
    )
    while True:
        await asyncio.sleep(min(refresher.cache_interval, 60.0))
        try:
            await refresher.sync_cache(interval=refresher.cache_interval)
            await refresher.reconcile()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ship review state reconciliation failed")
