"""Local HTTP API for the Clanker browser extension.

Auth is the caller's own Dashboard session token (``Authorization: Bearer <token>``). It is
only *validated*: one read-only workplace request proves it is a live session with Dashboard
access. It is cached (hashed) for a few minutes and never stored or used for anything else.
The only write is saving "Clanker was right/wrong" feedback. It never touches the Dashboard with
anyone's token beyond validating it: the extension attaches videos itself, from the dashboard page,
with the user's own session. A human submits the verdict in the dashboard.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from clanker.config import Settings
from clanker.results import ResultStore
from clanker.shipwrights import ShipwrightsClient
from clanker.shipwrights.client import AuthenticationError, ShipwrightsError

TokenValidator = Callable[[str], Awaitable[bool]]
VALID_TTL = 300.0

logger = logging.getLogger(__name__)

STORE = web.AppKey("store", ResultStore)
SETTINGS = web.AppKey("settings", Settings)
VALIDATOR = web.AppKey("validator", Callable)
AUTH_CACHE = web.AppKey("auth_cache", dict)


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
    }
    if request.method == "OPTIONS":
        return web.Response(headers=cors)
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not supplied or not await _is_valid(request.app, supplied):
        return web.json_response({"error": "unauthorized"}, status=401, headers=cors)
    response = await handler(request)
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


def build_api(
    settings: Settings, store: ResultStore, validator: TokenValidator | None = None
) -> web.Application:
    app = web.Application(middlewares=[_auth_and_cors])
    app[STORE] = store
    app[SETTINGS] = settings
    app[VALIDATOR] = validator or dashboard_validator(settings)
    app[AUTH_CACHE] = {}
    app.router.add_get("/api/results", list_results)
    app.router.add_get("/api/feedback.jsonl", get_feedback_export)
    app.router.add_get("/api/results/{cert_id}", get_result)
    app.router.add_get("/api/results/{cert_id}/video", get_video)
    app.router.add_post("/api/results/{cert_id}/feedback", post_feedback)
    return app


async def run_extension_api(settings: Settings, store: ResultStore) -> None:
    import asyncio

    runner = web.AppRunner(build_api(settings, store))
    await runner.setup()
    await web.TCPSite(runner, settings.extension_api_host, settings.extension_api_port).start()
    logger.info(
        "Extension API on http://%s:%d", settings.extension_api_host, settings.extension_api_port
    )
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
