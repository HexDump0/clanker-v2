from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from aiohttp.test_utils import TestClient, TestServer

from clanker.api import build_api
from clanker.config import Settings
from clanker.identity import Identity
from clanker.results import ResultStore
from clanker.review.models import ReviewVerdict
from clanker.shipwrights import ShipwrightsClient

TOKEN = "t0ken"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
VALIDATIONS: list[str] = []


USER = Identity(id="u1", name="Tester", slack_id="U123", slack_username="tester")


async def fake_validator(token: str) -> Identity | None:
    VALIDATIONS.append(token)
    return USER if token == TOKEN else None


def make_outcome(cert_id="c1", verdict="REJECT", video=None):
    cert = SimpleNamespace(project_name="Proj", repo_url="https://g/x", demo_url=None)
    return SimpleNamespace(
        cert_id=cert_id,
        packet=SimpleNamespace(cert=cert, stardance_url="https://s/1"),
        review=SimpleNamespace(verdict=ReviewVerdict.REJECT, reasoning="r", required_fixes=None),
        first_layer=SimpleNamespace(
            verdict=verdict, summary="sum", reasons=["no_readme"], unsure=[]
        ),
        reject_message="fix your readme",
        video_path=video,
        pdf_path=None,
    )


@pytest.fixture
def store(tmp_path):
    return ResultStore(tmp_path / "results")


@pytest.fixture
async def api(store, tmp_path):
    VALIDATIONS.clear()
    settings = Settings(shipwrights_session="x")
    async with TestClient(TestServer(build_api(settings, store, fake_validator))) as c:
        yield c


def test_store_roundtrip_and_feedback_survives_rerun(store):
    store.save_outcome(make_outcome())
    store.set_feedback("c1", "wrong", note="readme exists", wrong_checks=["no_readme"])
    store.save_outcome(make_outcome())  # same result: the human label stays
    assert store.get("c1").feedback.agreement == "wrong"
    assert '"readme exists"' in store.export_feedback_jsonl()
    store.save_outcome(make_outcome(verdict="APPROVE"))  # verdict changed: label no longer applies
    assert store.get("c1").feedback is None


def test_store_rejects_path_traversal(store):
    with pytest.raises(ValueError):
        store.get("../etc/passwd")


async def test_requires_token(api):
    assert (await api.get("/api/results")).status == 401
    assert (await api.get("/api/results", headers={"Authorization": "Bearer nope"})).status == 401


async def test_list_filter_and_feedback(api, store):
    store.save_outcome(make_outcome("a", "REJECT"))
    store.save_outcome(make_outcome("b", "APPROVE"))
    resp = await api.get("/api/results?verdict=REJECT", headers=AUTH)
    assert [r["cert_id"] for r in await resp.json()] == ["a"]
    bad = await api.post("/api/results/a/feedback", json={"agreement": "maybe"}, headers=AUTH)
    assert bad.status == 400
    ok = await api.post("/api/results/a/feedback", json={"agreement": "right"}, headers=AUTH)
    assert (await ok.json())["feedback"]["agreement"] == "right"
    assert (await api.get("/api/results/zzz", headers=AUTH)).status == 404


async def test_results_carry_queue_membership(store, tmp_path):
    store.save_outcome(make_outcome("decided", "REJECT"))
    store.save_outcome(make_outcome("untouched", "APPROVE"))
    store.set_review_state("decided", decision="returned", waiting=False)

    async with TestClient(
        TestServer(build_api(Settings(shipwrights_session="x"), store, fake_validator))
    ) as c:
        listed = {r["cert_id"]: r for r in await (await c.get("/api/results", headers=AUTH)).json()}

    assert listed["decided"]["in_queue"] is False
    assert listed["decided"]["decision"] == "returned"
    assert listed["untouched"]["in_queue"] is True
    assert listed["untouched"]["decision"] is None


async def test_listing_refreshes_ship_states_first(store):
    """The queue is only correct if /api/results brings the review states up to date."""
    calls = []

    async def refresh():
        calls.append(1)
        store.set_review_state("c1", decision="approved", waiting=False)

    async with TestClient(
        TestServer(
            build_api(Settings(shipwrights_session="x"), store, fake_validator, refresh=refresh)
        )
    ) as c:
        store.save_outcome(make_outcome("c1", "REJECT"))
        listed = await (await c.get("/api/results", headers=AUTH)).json()

    assert calls == [1]
    assert listed[0]["in_queue"] is False  # the refresh landed before the response


async def test_a_broken_refresh_still_serves_results(store):
    async def refresh():
        raise RuntimeError("stardance is down")

    async with TestClient(
        TestServer(
            build_api(Settings(shipwrights_session="x"), store, fake_validator, refresh=refresh)
        )
    ) as c:
        store.save_outcome(make_outcome("c1", "REJECT"))
        resp = await c.get("/api/results", headers=AUTH)
        assert resp.status == 200
        assert (await resp.json())[0]["in_queue"] is True  # stale, but served


async def test_valid_token_is_cached_but_bad_one_is_rechecked(api):
    for _ in range(3):
        assert (await api.get("/api/results", headers=AUTH)).status == 200
    assert VALIDATIONS == [TOKEN]
    bad = {"Authorization": "Bearer nope"}
    await api.get("/api/results", headers=bad)
    await api.get("/api/results", headers=bad)
    assert VALIDATIONS.count("nope") == 1  # bad tokens are remembered too (no Dashboard hammering)
    assert (await api.get(f"/api/results?token={TOKEN}")).status == 401


async def test_dashboard_validator_accepts_live_session_and_rejects_401(monkeypatch):
    from clanker.api import dashboard_validator

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("cookie") == "session=good":
            return httpx.Response(200, json={"slug": "stardance"})
        return httpx.Response(401, json={"error": "no"})

    real_init = ShipwrightsClient.__init__
    monkeypatch.setattr(
        ShipwrightsClient,
        "__init__",
        lambda self, **kw: real_init(self, **{**kw, "transport": httpx.MockTransport(handler)}),
    )
    validate = dashboard_validator(Settings(shipwrights_session="x"))
    good = await validate("good")
    assert good is not None and good.name == "a reviewer"  # not a JWT: generic identity
    assert await validate("bad") is None


async def test_request_review_runs_once_then_cools_down(store, tmp_path):
    import asyncio

    release = asyncio.Event()
    calls: list[str] = []

    async def review(cert_id: str, who: str | None = None) -> None:
        calls.append(cert_id)
        await release.wait()
        store.save_outcome(make_outcome(cert_id))

    VALIDATIONS.clear()
    app = build_api(
        Settings(shipwrights_session="x", extension_usage_file=tmp_path / "usage.json"),
        store,
        fake_validator,
        review,
    )
    async with TestClient(TestServer(app)) as c:
        first = await c.post("/api/results/new1/review", headers=AUTH)
        assert first.status == 202 and (await first.json())["state"] == "running"
        again = await c.post("/api/results/new1/review", headers=AUTH)
        assert again.status == 202 and calls == ["new1"]  # not started twice
        status = await (await c.get("/api/results/new1/review-status", headers=AUTH)).json()
        assert status["state"] == "running"
        release.set()
        for _ in range(50):
            status = await (await c.get("/api/results/new1/review-status", headers=AUTH)).json()
            if status["state"] != "running":
                break
            await asyncio.sleep(0.01)
        assert status["state"] == "idle" and store.get("new1") is not None
        assert (await c.post("/api/results/new1/review", headers=AUTH)).status == 429
        assert (await c.post("/api/results/..%2fx/review", headers=AUTH)).status in (400, 404)


async def test_failed_review_reports_error(store, tmp_path):
    async def review(cert_id: str, who: str | None = None) -> None:
        raise RuntimeError("cert not found")

    app = build_api(
        Settings(shipwrights_session="x", extension_usage_file=tmp_path / "usage.json"),
        store,
        fake_validator,
        review,
    )
    async with TestClient(TestServer(app)) as c:
        await c.post("/api/results/bad1/review", headers=AUTH)
        import asyncio

        await asyncio.sleep(0.05)
        status = await (await c.get("/api/results/bad1/review-status", headers=AUTH)).json()
        assert status == {"state": "failed", "error": "cert not found"}


async def test_request_review_unavailable_without_runner(api):
    assert (await api.post("/api/results/x1/review", headers=AUTH)).status == 503


async def test_preflight_allows_private_network_access(api):
    resp = await api.options(
        "/api/results/x",
        headers={
            "Origin": "https://ds.shipwrights.dev",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Private-Network": "true",
        },
    )
    assert resp.status == 200
    assert resp.headers["Access-Control-Allow-Private-Network"] == "true"
    assert "Authorization" in resp.headers["Access-Control-Allow-Headers"]


async def test_error_responses_still_carry_cors_headers(api):
    missing = await api.get(
        "/api/results/nope", headers={**AUTH, "Origin": "https://ds.shipwrights.dev"}
    )
    assert missing.status == 404
    assert missing.headers["Access-Control-Allow-Origin"] == "*"


def test_reason_codes_get_human_labels(store):
    store.save_outcome(make_outcome())
    rec = store.get("c1")
    assert rec.reasons == ["no_readme"] and rec.reason_labels == ["no README"]


async def test_pdf_is_served_only_when_the_result_has_one(api, store, tmp_path):
    pdf = tmp_path / "c1.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    outcome = make_outcome("c1")
    outcome.pdf_path = pdf
    store.save_outcome(outcome)
    store.save_outcome(make_outcome("c2"))  # no pdf
    ok = await api.get("/api/results/c1/pdf", headers=AUTH)
    assert ok.status == 200 and ok.headers["Content-Type"] == "application/pdf"
    assert await ok.read() == b"%PDF-1.4 fake"
    assert (await api.get("/api/results/c2/pdf", headers=AUTH)).status == 404


def test_wrong_label_means_manual_review_and_clearing_undoes_it(store):
    store.save_outcome(make_outcome())
    assert store.get("c1").manual_review is False
    store.set_feedback("c1", "right")
    assert store.get("c1").manual_review is False  # right is info only
    store.set_feedback("c1", "wrong", note="has a README")
    assert store.get("c1").manual_review is True
    assert '"manual_review":true' in store.get("c1").model_dump_json()
    store.clear_feedback("c1")
    assert store.get("c1").feedback is None and store.get("c1").manual_review is False


def test_slack_thread_survives_a_rereview(store):
    store.save_outcome(make_outcome())
    store.set_slack_ts("c1", "1.2")
    store.save_outcome(make_outcome(verdict="APPROVE"))
    assert store.get("c1").slack_ts == "1.2"


async def test_wrong_notifies_once_on_the_change_and_right_never(store):
    flagged: list[str] = []

    async def flag(record) -> None:
        flagged.append(record.cert_id)

    store.save_outcome(make_outcome())
    app = build_api(Settings(shipwrights_session="x"), store, fake_validator, on_manual_review=flag)
    async with TestClient(TestServer(app)) as c:
        post = lambda body: c.post("/api/results/c1/feedback", json=body, headers=AUTH)  # noqa: E731
        assert (await post({"agreement": "right"})).status == 200
        await post({"agreement": "wrong", "note": "has a README"})
        await post({"agreement": "wrong", "note": "edited note"})  # still wrong: no re-notify
        resp = await post({"agreement": "clear"})
        assert (await resp.json())["manual_review"] is False
        await post({"agreement": "wrong"})  # flagged again after being cleared
        import asyncio

        await asyncio.sleep(0.05)
    assert flagged == ["c1", "c1"]
