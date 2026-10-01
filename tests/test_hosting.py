from __future__ import annotations

import base64
import json
import time

import pytest
from aiohttp.test_utils import TestClient, TestServer

from clanker.api import MAX_AUTH_FAILURES, build_api
from clanker.budget import UsageLimiter
from clanker.config import Settings
from clanker.identity import Identity, identity_from_token, token_expired
from clanker.results import ResultStore
from tests.test_extension_api import AUTH, USER, fake_validator, make_outcome


def jwt(payload: dict) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{enc({'alg': 'HS256'})}.{enc(payload)}.sig"


# ---------------------------------------------------------------- identity
def test_identity_comes_from_the_token_claims_and_skips_the_email():
    token = jwt(
        {
            "exp": time.time() + 3600,
            "user": {
                "id": "u9",
                "slackId": "U9",
                "email": "x@y.z",
                "slackUsername": "jo",
                "displayName": "Jo D",
            },
        }
    )
    who = identity_from_token(token)
    assert who == Identity(id="u9", name="Jo D", slack_id="U9", slack_username="jo")
    assert "x@y.z" not in repr(who)


def test_identity_handles_garbage_and_expiry():
    assert identity_from_token("not-a-jwt") is None
    assert identity_from_token(jwt({"user": {}})) is None
    assert token_expired(jwt({"exp": time.time() - 5})) is True
    assert token_expired(jwt({"exp": time.time() + 500})) is False
    assert token_expired("garbage") is False


def test_allow_list_matches_any_identifier_case_insensitively():
    who = Identity(id="u9", name="Jo D", slack_id="U9", slack_username="Jo")
    assert who.matches({"jo"}) and who.matches({"u9"}) and not who.matches({"someone-else"})


# ------------------------------------------------------------------ budget
def test_budget_limits_per_user_and_overall_and_survives_restart(tmp_path):
    path = tmp_path / "usage.json"
    limiter = UsageLimiter(path, per_user=2, per_day=3, today=lambda: "2026-10-01")
    assert limiter.try_use("a") is None and limiter.try_use("a") is None
    assert "2 reviews" in limiter.try_use("a")  # a is out
    assert limiter.left("a") == 0 and limiter.left("b") == 1
    assert limiter.try_use("b") is None
    assert "daily review limit" in limiter.try_use("c")  # 3 overall
    again = UsageLimiter(path, per_user=2, per_day=3, today=lambda: "2026-10-01")
    assert again.left("a") == 0  # a restart does not hand out a fresh budget
    tomorrow = UsageLimiter(path, per_user=2, per_day=3, today=lambda: "2026-10-02")
    assert tomorrow.left("a") == 2


def test_zero_means_unlimited(tmp_path):
    limiter = UsageLimiter(None, per_user=0, per_day=0)
    assert all(limiter.try_use("a") is None for _ in range(50)) and limiter.left("a") is None


# --------------------------------------------------------------------- API
@pytest.fixture
def store(tmp_path):
    return ResultStore(tmp_path / "results")


def settings(tmp_path, **kw):
    return Settings(shipwrights_session="x", extension_usage_file=tmp_path / "u.json", **kw)


async def test_healthz_needs_no_token(store, tmp_path):
    app = build_api(settings(tmp_path), store, fake_validator)
    async with TestClient(TestServer(app)) as c:
        resp = await c.get("/healthz")
        assert resp.status == 200 and (await resp.json()) == {"ok": True}


async def test_allow_list_blocks_other_dashboard_users(store, tmp_path):
    app = build_api(
        settings(tmp_path, extension_allowed_users="someone-else, U123"), store, fake_validator
    )
    async with TestClient(TestServer(app)) as c:
        assert (await c.get("/api/me", headers=AUTH)).status == 200  # Slack id U123 is listed
    app = build_api(settings(tmp_path, extension_allowed_users="nobody"), store, fake_validator)
    async with TestClient(TestServer(app)) as c:
        assert (await c.get("/api/me", headers=AUTH)).status == 403


async def test_repeated_bad_tokens_get_throttled_without_hitting_the_dashboard(store, tmp_path):
    calls: list[str] = []

    async def counting(token: str):
        calls.append(token)
        return None

    app = build_api(settings(tmp_path), store, counting)
    async with TestClient(TestServer(app)) as c:
        for i in range(MAX_AUTH_FAILURES):
            assert (
                await c.get("/api/me", headers={"Authorization": f"Bearer bad{i}"})
            ).status == 401
        assert (await c.get("/api/me", headers={"Authorization": "Bearer bad-more"})).status == 429
    assert len(calls) == MAX_AUTH_FAILURES  # the throttled one never reached the validator


async def test_review_budget_is_charged_once_and_reported(store, tmp_path):
    ran: list[tuple[str, str | None]] = []

    async def review(cert_id: str, who: str | None) -> None:
        ran.append((cert_id, who))

    limiter = UsageLimiter(None, per_user=2, per_day=0)
    app = build_api(settings(tmp_path), store, fake_validator, review, limiter=limiter)
    async with TestClient(TestServer(app)) as c:
        assert (await c.get("/api/me", headers=AUTH)).status == 200
        me = await (await c.get("/api/me", headers=AUTH)).json()
        assert me == {"id": "u1", "name": "Tester", "reviews_left": 2}
        assert (await c.post("/api/results/s1/review", headers=AUTH)).status == 202
        assert (await c.post("/api/results/s2/review", headers=AUTH)).status == 202
        third = await c.post("/api/results/s3/review", headers=AUTH)
        assert third.status == 429 and "2 reviews" in (await third.json())["error"]
        import asyncio

        await asyncio.sleep(0.05)
    assert ran == [("s1", "Tester"), ("s2", "Tester")]  # the requester is passed along


async def test_feedback_records_who_gave_it(store, tmp_path):
    store.save_outcome(make_outcome())
    app = build_api(settings(tmp_path), store, fake_validator)
    async with TestClient(TestServer(app)) as c:
        resp = await c.post("/api/results/c1/feedback", json={"agreement": "right"}, headers=AUTH)
        fb = (await resp.json())["feedback"]
    assert fb["by_id"] == "u1" and fb["by_name"] == "Tester"
    assert USER.name in store.export_feedback_jsonl()
