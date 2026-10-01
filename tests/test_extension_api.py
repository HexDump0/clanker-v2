from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from aiohttp.test_utils import TestClient, TestServer

from clanker.api import build_api
from clanker.config import Settings
from clanker.results import ResultStore
from clanker.review.models import ReviewVerdict
from clanker.shipwrights import ShipwrightsClient

TOKEN = "t0ken"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
VALIDATIONS: list[str] = []


async def fake_validator(token: str) -> bool:
    VALIDATIONS.append(token)
    return token == TOKEN


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
    store.save_outcome(make_outcome(verdict="APPROVE"))  # re-review keeps the human label
    rec = store.get("c1")
    assert rec.verdict == "APPROVE" and rec.feedback.agreement == "wrong"
    assert '"readme exists"' in store.export_feedback_jsonl()


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


async def test_valid_token_is_cached_but_bad_one_is_rechecked(api):
    for _ in range(3):
        assert (await api.get("/api/results", headers=AUTH)).status == 200
    assert VALIDATIONS == [TOKEN]
    bad = {"Authorization": "Bearer nope"}
    await api.get("/api/results", headers=bad)
    await api.get("/api/results", headers=bad)
    assert VALIDATIONS.count("nope") == 2
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
    assert await validate("good") is True
    assert await validate("bad") is False
