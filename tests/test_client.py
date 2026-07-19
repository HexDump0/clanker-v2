from __future__ import annotations

import httpx
import pytest

from clanker.shipwrights import (
    AuthenticationError,
    CertStatus,
    MutationNotAllowedError,
    NotFoundError,
    ShipwrightsClient,
    Verdict,
)
from tests.conftest import FakeDashboard, make_cert


async def test_list_certifications(client, dashboard):
    dashboard.set_pending([make_cert("c1"), make_cert("c2")])
    page = await client.list_certifications(status=CertStatus.PENDING)
    assert page.total == 2
    assert [c.id for c in page.certs] == ["c1", "c2"]
    assert page.certs[0].project_name == "Project c1"
    assert page.certs[0].status is CertStatus.PENDING
    # status param actually sent
    assert dashboard.requests[-1].url.params["status"] == "PENDING"


async def test_iter_certifications_walks_all_pages(client, dashboard):
    dashboard.set_pending([make_cert(f"c{i}") for i in range(120)], per_page=50)
    ids = [c.id async for c in client.iter_certifications(status=CertStatus.PENDING)]
    assert len(ids) == 120
    assert len({r.url.params["page"] for r in dashboard.requests}) == 3


async def test_get_certification_and_readme(client, dashboard):
    dashboard.details["c1"] = {
        **make_cert("c1"),
        "reviews": [
            {
                "id": "r1",
                "certId": "c1",
                "verdict": "APPROVED",
                "comment": "nice",
                "createdAt": "2026-07-18T00:00:00.000Z",
                "reviewer": {"displayName": None, "slackUsername": "rev"},
            }
        ],
        "feedbackRequired": True,
    }
    detail = await client.get_certification("c1")
    assert detail.feedback_required is True
    assert detail.reviews[0].verdict is Verdict.APPROVED
    assert await client.get_readme("c1") == "# Hi"


async def test_not_found(client):
    with pytest.raises(NotFoundError):
        await client.get_certification("nope")


async def test_redirect_means_expired_session(dashboard):
    def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(307, headers={"location": "/login"})

    client = ShipwrightsClient(
        base_url="https://ds.shipwrights.dev",
        session_cookie="expired",
        transport=httpx.MockTransport(redirect),
    )
    with pytest.raises(AuthenticationError):
        await client.list_certifications()


def test_empty_cookie_rejected():
    with pytest.raises(AuthenticationError):
        ShipwrightsClient(base_url="https://x", session_cookie="")


async def test_mutations_blocked_by_default(client):
    with pytest.raises(MutationNotAllowedError):
        await client.claim("c1")
    with pytest.raises(MutationNotAllowedError):
        await client.submit_review("c1", Verdict.APPROVED, "great work")
    with pytest.raises(MutationNotAllowedError):
        await client.set_internal_notes("c1", "note")


async def test_claim_when_mutations_allowed(dashboard: FakeDashboard):
    dashboard.details["c1"] = make_cert("c1")
    client = ShipwrightsClient(
        base_url="https://ds.shipwrights.dev",
        session_cookie="test-jwt",
        allow_mutations=True,
        transport=httpx.MockTransport(dashboard.handler),
    )
    detail = await client.claim("c1")
    assert detail.status is CertStatus.IN_REVIEW


async def test_review_requires_comment(dashboard: FakeDashboard):
    client = ShipwrightsClient(
        base_url="https://ds.shipwrights.dev",
        session_cookie="test-jwt",
        allow_mutations=True,
        transport=httpx.MockTransport(dashboard.handler),
    )
    with pytest.raises(ValueError):
        await client.submit_review("c1", Verdict.REJECTED, "   ")
