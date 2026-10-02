"""Local HTTP API for the Clanker browser extension.

Auth is the caller's own Dashboard session token (``Authorization: Bearer <token>``). It is
only *validated*: one read-only workplace request proves it is a live session with Dashboard
access. The result is cached (hashed) for a few minutes; the token is never stored or used for
anything else. Who the caller is comes from the claims in that validated token (``identity``).
Everything the server itself does on the Dashboard (reviews, Slack, the watcher) uses the
credentials in ``.env``, never a caller's token.
The only writes are right/wrong labels ("wrong" flags the ship for manual review and tells Slack)
and queueing a Clanker review a user asked for. The extension attaches videos itself, from the
dashboard page, with the user's own session. A human submits the verdict in the dashboard.

``refresh`` is an optional coroutine that brings each record's review state up to date before
the list is served; it never raises, so a Dashboard/Stardance outage returns the last known
states instead of failing the request.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from aiohttp import web

from clanker.budget import UsageLimiter
from clanker.config import Settings
from clanker.identity import Identity, identity_from_token, token_expired
from clanker.results import ResultRecord, ResultStore, is_valid_id
from clanker.shipwrights import ShipwrightsClient
from clanker.shipwrights.client import AuthenticationError, ShipwrightsError

TokenValidator = Callable[[str], Awaitable["Identity | None"]]
ReviewFn = Callable[[str, "str | None"], Awaitable[object]]
ManualReviewFn = Callable[[ResultRecord], Awaitable[object]]
RefreshFn = Callable[[], Awaitable[object]]
VALID_TTL = 300.0
INVALID_TTL = 60.0  # remember bad tokens so strangers can't make us hammer the Dashboard
MAX_AUTH_FAILURES = 20  # per client IP per minute
REVIEW_COOLDOWN = 60.0  # seconds before the same cert can be re-requested

logger = logging.getLogger(__name__)

STORE = web.AppKey("store", ResultStore)
SETTINGS = web.AppKey("settings", Settings)
VALIDATOR = web.AppKey("validator", Callable)
JOBS = web.AppKey("jobs", object)
FLAG = web.AppKey("flag", object)
AUTH_CACHE = web.AppKey("auth_cache", dict)
AUTH_FAILS = web.AppKey("auth_fails", dict)
LIMITER = web.AppKey("limiter", object)
BG = web.AppKey("bg", set)
REFRESH = web.AppKey("refresh", object)


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

    def start(self, cert_id: str, who: str | None = None) -> bool:
        """Begin a review; False if one is already running for this cert."""
        if self.status(cert_id)["state"] == "running":
            return False
        self._status[cert_id] = {"state": "running"}
        task = asyncio.create_task(self._run(cert_id, who), name=f"ext-review-{cert_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def _run(self, cert_id: str, who: str | None) -> None:
        try:
            async with self._semaphore:
                await self._review(cert_id, who)
            self._status[cert_id] = {"state": "idle", "finished": time.monotonic()}
        except Exception as exc:
            logger.exception("Extension-requested review failed for cert %s", cert_id)
            self._status[cert_id] = {
                "state": "failed",
                "error": str(exc) or type(exc).__name__,
                "finished": time.monotonic(),
            }


def dashboard_validator(settings: Settings) -> TokenValidator:
    """Check a token against the real Dashboard (read-only); returns who it belongs to."""

    async def validate(token: str) -> Identity | None:
        if token_expired(token):
            return None  # no need to bother the Dashboard
        try:
            async with ShipwrightsClient(
                base_url=settings.shipwrights_base_url,
                session_cookie=token,
                workplace=settings.shipwrights_workplace,
            ) as sw:
                await sw.get_workplace()
        except AuthenticationError:
            return None
        except ShipwrightsError:
            logger.warning("Dashboard error while validating a token", exc_info=True)
            return None
        # The Dashboard accepted the token, so the claims inside it are genuine.
        return identity_from_token(token) or Identity(
            id="u-" + hashlib.sha256(token.encode()).hexdigest()[:12], name="a reviewer"
        )

    return validate


def _client_ip(request: web.Request) -> str:
    if request.app[SETTINGS].extension_api_trust_proxy:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.remote or "?"


def _too_many_failures(app: web.Application, ip: str) -> bool:
    now = time.monotonic()
    recent = [t for t in app[AUTH_FAILS].get(ip, []) if now - t < 60.0]
    app[AUTH_FAILS][ip] = recent
    return len(recent) >= MAX_AUTH_FAILURES


async def _identify(app: web.Application, token: str) -> Identity | None:
    key = hashlib.sha256(token.encode()).hexdigest()
    cache: dict[str, tuple[float, Identity | None]] = app[AUTH_CACHE]
    hit = cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    identity = await app[VALIDATOR](token)
    ttl = VALID_TTL if identity else INVALID_TTL
    cache[key] = (time.monotonic() + ttl, identity)
    if len(cache) > 2000:  # keep memory bounded
        for k in [k for k, (exp, _) in cache.items() if exp < time.monotonic()]:
            del cache[k]
    return identity


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
    if request.path == "/healthz":  # for the proxy / uptime checks; reveals nothing
        return web.json_response({"ok": True}, headers=cors)
    ip = _client_ip(request)
    if _too_many_failures(request.app, ip):
        return web.json_response(
            {"error": "too many failed attempts, slow down"}, status=429, headers=cors
        )
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    identity = await _identify(request.app, supplied) if supplied else None
    if identity is None:
        request.app[AUTH_FAILS].setdefault(ip, []).append(time.monotonic())
        return web.json_response({"error": "unauthorized"}, status=401, headers=cors)
    allowed = {
        u.strip().lower()
        for u in request.app[SETTINGS].extension_allowed_users.split(",")
        if u.strip()
    }
    if allowed and not identity.matches(allowed):
        return web.json_response(
            {"error": "your account isn't allowed to use Clanker"}, status=403, headers=cors
        )
    request["user"] = identity
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
    # Bring ship review states up to date first (a couple of read-only Stardance requests,
    # skipped unless one is due), so the queue reflects what humans have decided. A failure
    # here must not fail the request: the extension gets the last known states instead.
    refresh = request.app.get(REFRESH)
    if refresh is not None:
        try:
            await refresh()
        except Exception:
            logger.warning("Could not refresh ship review states", exc_info=True)
    records = request.app[STORE].list(request.query.get("verdict"))
    return web.json_response([r.model_dump(mode="json") for r in records])


async def get_result(request: web.Request) -> web.Response:
    return web.json_response(_record_or_404(request).model_dump(mode="json"))


async def get_video(request: web.Request) -> web.StreamResponse:
    record = _record_or_404(request)
    if not record.video_path or not Path(record.video_path).is_file():
        raise web.HTTPNotFound(text="no video")
    return web.FileResponse(record.video_path)


async def get_pdf(request: web.Request) -> web.StreamResponse:
    record = _record_or_404(request)
    if not record.pdf_path or not Path(record.pdf_path).is_file():
        raise web.HTTPNotFound(text="no pdf")
    return web.FileResponse(record.pdf_path, headers={"Content-Type": "application/pdf"})


async def post_feedback(request: web.Request) -> web.Response:
    """Save a human label. "wrong" flags the ship for manual review (and tells Slack once)."""
    body = await request.json()
    agreement = body.get("agreement")
    if agreement not in ("right", "wrong", "clear"):
        return web.json_response(
            {"error": "agreement must be 'right', 'wrong' or 'clear'"}, status=400
        )
    previous = _record_or_404(request)
    store = request.app[STORE]
    cert_id = request.match_info["cert_id"]
    if agreement == "clear":
        record = store.clear_feedback(cert_id)
    else:
        record = store.set_feedback(
            cert_id,
            agreement,
            note=str(body.get("note", "")),
            wrong_checks=[str(c) for c in body.get("wrong_checks", [])],
            by=(request["user"].id, request["user"].name),
        )
    flag: ManualReviewFn | None = request.app[FLAG]
    if record.manual_review and not previous.manual_review and flag is not None:
        # Only on the change into "wrong", so editing the note doesn't re-notify everyone.
        task = asyncio.create_task(_flag(flag, record), name=f"manual-review-{cert_id}")
        request.app[BG].add(task)
        task.add_done_callback(request.app[BG].discard)
    return web.json_response(record.model_dump(mode="json"))


async def _flag(flag: ManualReviewFn, record: ResultRecord) -> None:
    try:
        await flag(record)
    except Exception:
        logger.exception("Could not announce manual review for cert %s", record.cert_id)


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
    if jobs.status(cert_id)["state"] == "running":
        return web.json_response(jobs.status(cert_id), status=202)  # already on it; no charge
    wait = jobs.cooldown_left(cert_id)
    if wait > 0:
        return web.json_response(
            {"error": f"reviewed a moment ago, try again in {wait:.0f}s"}, status=429
        )
    user: Identity = request["user"]
    if over := request.app[LIMITER].try_use(user.id):
        return web.json_response({"error": over}, status=429)
    jobs.start(cert_id, user.name)
    return web.json_response(jobs.status(cert_id), status=202)


async def get_me(request: web.Request) -> web.Response:
    user: Identity = request["user"]
    return web.json_response(
        {"id": user.id, "name": user.name, "reviews_left": request.app[LIMITER].left(user.id)}
    )


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
    on_manual_review: ManualReviewFn | None = None,
    limiter: UsageLimiter | None = None,
    refresh: RefreshFn | None = None,
) -> web.Application:
    app = web.Application(middlewares=[_auth_and_cors])
    app[STORE] = store
    app[SETTINGS] = settings
    app[VALIDATOR] = validator or dashboard_validator(settings)
    app[AUTH_CACHE] = {}
    app[AUTH_FAILS] = {}
    app[BG] = set()
    app[LIMITER] = limiter or UsageLimiter(
        settings.extension_usage_file,
        per_user=settings.extension_reviews_per_user_per_day,
        per_day=settings.extension_reviews_per_day,
    )
    app[FLAG] = on_manual_review
    app[REFRESH] = refresh
    app[JOBS] = ReviewJobs(review, settings.max_concurrent_reviews) if review else None
    app.router.add_get("/api/me", get_me)
    app.router.add_get("/api/results", list_results)
    app.router.add_get("/api/feedback.jsonl", get_feedback_export)
    app.router.add_get("/api/results/{cert_id}", get_result)
    app.router.add_get("/api/results/{cert_id}/video", get_video)
    app.router.add_get("/api/results/{cert_id}/pdf", get_pdf)
    app.router.add_post("/api/results/{cert_id}/feedback", post_feedback)
    app.router.add_post("/api/results/{cert_id}/review", post_review)
    app.router.add_get("/api/results/{cert_id}/review-status", get_review_status)
    return app


async def run_extension_api(
    settings: Settings,
    store: ResultStore,
    review: ReviewFn | None = None,
    on_manual_review: ManualReviewFn | None = None,
    refresh: RefreshFn | None = None,
) -> None:
    runner = web.AppRunner(
        build_api(
            settings, store, review=review, on_manual_review=on_manual_review, refresh=refresh
        )
    )
    await runner.setup()
    await web.TCPSite(runner, settings.extension_api_host, settings.extension_api_port).start()
    logger.info(
        "Extension API on http://%s:%d", settings.extension_api_host, settings.extension_api_port
    )
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
