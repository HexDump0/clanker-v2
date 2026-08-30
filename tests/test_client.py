from __future__ import annotations

import httpx
import pytest

from clanker.shipwrights import (
    AuthenticationError,
    CertStatus,
    CloudflareBlockError,
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
    assert not dashboard.requests[-1].headers["user-agent"].startswith("clanker/")


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


async def test_attempt_history_accepts_current_dashboard_shape(client, dashboard):
    dashboard.details["c1"] = {
        **make_cert("c1"),
        "reviews": [],
        "internalNotes": "Private reviewer lead",
        "attempts": [
            {
                "id": "old-attempt",
                "externalId": "10",
                "projectName": "Earlier name",
                "status": "REJECTED",
                "createdAt": "2026-07-01T00:00:00.000Z",
                "reviews": [
                    {
                        "verdict": "REJECTED",
                        "comment": "README was incomplete",
                        "createdAt": "2026-07-02T00:00:00.000Z",
                        "reviewerSlackId": "U1",
                        "reviewer": {
                            "slackId": "U1",
                            "displayName": "Reviewer",
                            "slackAvatar": "https://example.com/avatar.png",
                        },
                    }
                ],
            }
        ],
    }

    detail = await client.get_certification("c1")
    assert detail.internal_notes == "Private reviewer lead"
    assert detail.attempts[0].reviews[0].id is None
    assert detail.attempts[0].reviews[0].reviewer.slack_id == "U1"


async def test_feedback_templates_are_typed(client, dashboard):
    dashboard.feedback_templates["shared"] = [
        {"id": "t1", "title": "README", "body": "Please expand the README."}
    ]
    templates = await client.get_feedback_templates()
    assert templates.shared[0].title == "README"
    assert templates.reviewer_slack_username == "reviewer"


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


async def test_cloudflare_block_has_distinct_error():
    def blocked(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"server": "cloudflare", "content-type": "text/html"},
            text="<title>Attention Required! | Cloudflare</title> Sorry, you have been blocked",
        )

    client = ShipwrightsClient(
        base_url="https://ds.shipwrights.dev",
        session_cookie="valid-but-filtered",
        transport=httpx.MockTransport(blocked),
    )
    with pytest.raises(CloudflareBlockError):
        await client.list_certifications()


def test_empty_cookie_rejected():
    with pytest.raises(AuthenticationError):
        ShipwrightsClient(base_url="https://x", session_cookie="")


@pytest.mark.parametrize(
    "configured",
    ["jwt-value", "session=jwt-value", "last-workspace=stardance; session=jwt-value"],
)
async def test_dashboard_session_accepts_bare_or_pasted_cookie(configured):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["cookie"] == "session=jwt-value"
        return httpx.Response(200, json={"certs": [], "total": 0, "page": 1, "pages": 1})

    client = ShipwrightsClient(
        base_url="https://ds.shipwrights.dev",
        session_cookie=configured,
        transport=httpx.MockTransport(handler),
    )
    await client.list_certifications()


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
