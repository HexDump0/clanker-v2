"""Local HTTP API for the Clanker browser extension.

Auth is the caller's own Dashboard session token (``Authorization: Bearer <token>``). It is
only *validated*: one read-only workplace request proves it is a live session with Dashboard
access. It is cached (hashed) for a few minutes and never stored or used for anything else.
The only writes are "Clanker was right/wrong" feedback and queueing a Clanker review that a user
asked for (the extension's "Request review"). The extension attaches videos itself, from the
dashboard page, with the user's own session. A human submits the verdict in the dashboard.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from clanker.config import Settings
from clanker.results import ResultStore, is_valid_id
from clanker.shipwrights import ShipwrightsClient
from clanker.shipwrights.client import AuthenticationError, ShipwrightsError

TokenValidator = Callable[[str], Awaitable[bool]]
ReviewFn = Callable[[str], Awaitable[object]]
VALID_TTL = 300.0
REVIEW_COOLDOWN = 60.0  # seconds before the same cert can be re-requested

logger = logging.getLogger(__name__)

STORE = web.AppKey("store", ResultStore)
SETTINGS = web.AppKey("settings", Settings)
VALIDATOR = web.AppKey("validator", Callable)
JOBS = web.AppKey("jobs", object)
AUTH_CACHE = web.AppKey("auth_cache", dict)


class ReviewJobs:
    """Background review runs requested from the extension (one per cert at a time)."""

    def __init__(self, review: ReviewFn, concurrency: int) -> None:
        self._review = review
        self._semaphore = asyncio.Semaphore(concurrency)
        self._status: dict[str, dict[str, Any]] = {}
        self._tasks: set[asyncio.Task] = set()

    def status(self, cert_id: str) -> dict[str, Any]:
        entry = self._status.get(cert_id)
        return (
            {"state": entry["state"], "error": entry.get("error")} if entry else {"state": "idle"}
        )

    def cooldown_left(self, cert_id: str) -> float:
        entry = self._status.get(cert_id)
        if not entry or entry["state"] == "running":
            return 0.0
        return max(0.0, entry["finished"] + REVIEW_COOLDOWN - time.monotonic())

    def start(self, cert_id: str) -> bool:
        """Begin a review; False if one is already running for this cert."""
        if self.status(cert_id)["state"] == "running":
            return False
        self._status[cert_id] = {"state": "running"}
        task = asyncio.create_task(self._run(cert_id), name=f"ext-review-{cert_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def _run(self, cert_id: str) -> None:
        try:
            async with self._semaphore:
                await self._review(cert_id)
            self._status[cert_id] = {"state": "idle", "finished": time.monotonic()}
        except Exception as exc:
            logger.exception("Extension-requested review failed for cert %s", cert_id)
            self._status[cert_id] = {
                "state": "failed",
                "error": str(exc) or type(exc).__name__,
                "finished": time.monotonic(),
            }


def dashboard_validator(settings: Settings) -> TokenValidator:
    """Check a token against the real Dashboard (read-only) without keeping it."""

    async def validate(token: str) -> bool:
        try:
            async with ShipwrightsClient(
                base_url=settings.shipwrights_base_url,
                session_cookie=token,
                workplace=settings.shipwrights_workplace,
            ) as sw:
                await sw.get_workplace()
            return True
        except AuthenticationError:
            return False
        except ShipwrightsError:
            logger.warning("Dashboard error while validating a token", exc_info=True)
            return False

    return validate


async def _is_valid(app: web.Application, token: str) -> bool:
    key = hashlib.sha256(token.encode()).hexdigest()
    cache: dict[str, float] = app[AUTH_CACHE]
    if cache.get(key, 0.0) > time.monotonic():
        return True
    if not await app[VALIDATOR](token):
        cache.pop(key, None)
        return False
    cache[key] = time.monotonic() + VALID_TTL
    return True


@web.middleware
async def _auth_and_cors(request: web.Request, handler: Any) -> web.StreamResponse:
    cors = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        # Chrome blocks a public https page (the dashboard) from reaching 127.0.0.1 unless the
        # preflight opts in (Private Network Access).
        "Access-Control-Allow-Private-Network": "true",
    }
    if request.method == "OPTIONS":
        return web.Response(headers=cors)
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not supplied or not await _is_valid(request.app, supplied):
        return web.json_response({"error": "unauthorized"}, status=401, headers=cors)
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        # Raised responses (404 etc.) skip the normal path; without CORS headers the browser
        # reports a CORS failure instead of the real status.
        exc.headers.update(cors)
        raise
    response.headers.update(cors)
    return response


def _record_or_404(request: web.Request):
    try:
        record = request.app[STORE].get(request.match_info["cert_id"])
    except ValueError:  # malformed id
        record = None
    if record is None:
        raise web.HTTPNotFound(
            text='{"error": "no result for that cert"}', content_type="application/json"
        )
    return record


async def list_results(request: web.Request) -> web.Response:
    records = request.app[STORE].list(request.query.get("verdict"))
    return web.json_response([r.model_dump(mode="json") for r in records])


async def get_result(request: web.Request) -> web.Response:
    return web.json_response(_record_or_404(request).model_dump(mode="json"))


async def get_video(request: web.Request) -> web.StreamResponse:
    record = _record_or_404(request)
    if not record.video_path:
        raise web.HTTPNotFound(text="no video")
    return web.FileResponse(record.video_path)


async def post_feedback(request: web.Request) -> web.Response:
    body = await request.json()
    agreement = body.get("agreement")
    if agreement not in ("right", "wrong"):
        return web.json_response({"error": "agreement must be 'right' or 'wrong'"}, status=400)
    _record_or_404(request)
    record = request.app[STORE].set_feedback(
        request.match_info["cert_id"],
        agreement,
        note=str(body.get("note", "")),
        wrong_checks=[str(c) for c in body.get("wrong_checks", [])],
    )
    return web.json_response(record.model_dump(mode="json"))


async def get_feedback_export(request: web.Request) -> web.Response:
    return web.Response(
        text=request.app[STORE].export_feedback_jsonl(), content_type="application/x-ndjson"
    )


async def post_review(request: web.Request) -> web.Response:
    """Request (or re-request) a Clanker review. The result replaces any earlier one."""
    jobs: ReviewJobs | None = request.app[JOBS]
    cert_id = request.match_info["cert_id"]
    if jobs is None:
        return web.json_response({"error": "reviews cannot be requested here"}, status=503)
    if not is_valid_id(cert_id):
        return web.json_response({"error": "invalid cert id"}, status=400)
    wait = jobs.cooldown_left(cert_id)
    if wait > 0:
        return web.json_response(
            {"error": f"reviewed a moment ago, try again in {wait:.0f}s"}, status=429
        )
    jobs.start(cert_id)  # already running: just report running
    return web.json_response(jobs.status(cert_id), status=202)


async def get_review_status(request: web.Request) -> web.Response:
    jobs: ReviewJobs | None = request.app[JOBS]
    if jobs is None:
        return web.json_response({"state": "idle"})
    return web.json_response(jobs.status(request.match_info["cert_id"]))


def build_api(
    settings: Settings,
    store: ResultStore,
    validator: TokenValidator | None = None,
    review: ReviewFn | None = None,
) -> web.Application:
    app = web.Application(middlewares=[_auth_and_cors])
    app[STORE] = store
    app[SETTINGS] = settings
    app[VALIDATOR] = validator or dashboard_validator(settings)
    app[AUTH_CACHE] = {}
    app[JOBS] = ReviewJobs(review, settings.max_concurrent_reviews) if review else None
    app.router.add_get("/api/results", list_results)
    app.router.add_get("/api/feedback.jsonl", get_feedback_export)
    app.router.add_get("/api/results/{cert_id}", get_result)
    app.router.add_get("/api/results/{cert_id}/video", get_video)
    app.router.add_post("/api/results/{cert_id}/feedback", post_feedback)
    app.router.add_post("/api/results/{cert_id}/review", post_review)
    app.router.add_get("/api/results/{cert_id}/review-status", get_review_status)
    return app


async def run_extension_api(
    settings: Settings, store: ResultStore, review: ReviewFn | None = None
) -> None:
    runner = web.AppRunner(build_api(settings, store, review=review))
    await runner.setup()
    await web.TCPSite(runner, settings.extension_api_host, settings.extension_api_port).start()
    logger.info(
        "Extension API on http://%s:%d", settings.extension_api_host, settings.extension_api_port
    )
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
