from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from clanker.shipwrights import ShipwrightsClient


def make_cert(cert_id: str, **overrides: Any) -> dict[str, Any]:
    cert = {
        "id": cert_id,
        "projectName": f"Project {cert_id}",
        "projectType": "Web App",
        "status": "PENDING",
        "submitterSlackId": "U123",
        "submitterUsername": "tester",
        "demoUrl": "https://example.com",
        "repoUrl": "https://github.com/x/y",
        "devTime": "11h 21m",
        "hackatimeProjects": ["proj"],
        "createdAt": "2026-07-18T00:00:00.000Z",
        "_count": {"reviews": 0},
    }
    cert.update(overrides)
    return cert


class FakeDashboard:
    """In-memory stand-in for ds.shipwrights.dev, driving httpx.MockTransport."""

    def __init__(self) -> None:
        self.pages: list[list[dict[str, Any]]] = [[]]
        self.details: dict[str, dict[str, Any]] = {}
        self.requests: list[httpx.Request] = []
        self.feedback_templates: dict[str, Any] = {
            "shared": [],
            "mine": [],
            "reviewerSlackUsername": "reviewer",
        }
        self.leaderboard: dict[str, Any] = {"entries": []}

    def set_pending(self, certs: list[dict[str, Any]], per_page: int = 50) -> None:
        self.pages = [certs[i : i + per_page] for i in range(0, len(certs), per_page)] or [[]]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        prefix = "/api/v1/workplaces/stardance"

        if path == f"{prefix}/certifications" and request.method == "GET":
            page = int(request.url.params.get("page", "1"))
            certs = self.pages[page - 1] if page <= len(self.pages) else []
            total = sum(len(p) for p in self.pages)
            return httpx.Response(
                200,
                json={
                    "certs": certs,
                    "total": total,
                    "page": page,
                    "pages": len(self.pages),
                    "stats": {"PENDING": total},
                },
            )

        if path == f"{prefix}/feedback-templates" and request.method == "GET":
            return httpx.Response(200, json=self.feedback_templates)

        if path == f"{prefix}/certifications/leaderboard" and request.method == "GET":
            return httpx.Response(200, json=self.leaderboard)

        for cert_id, detail in self.details.items():
            if path == f"{prefix}/certifications/{cert_id}":
                return httpx.Response(200, json=detail)
            if path == f"{prefix}/certifications/{cert_id}/readme":
                return httpx.Response(
                    200, json={"status": "ok", "cached": True, "markdown": "# Hi"}
                )
            if path == f"{prefix}/certifications/{cert_id}/claim":
                body = json.loads(request.content)
                status = "PENDING" if body.get("unclaim") else "IN_REVIEW"
                return httpx.Response(200, json={**detail, "status": status})

        return httpx.Response(404, json={"error": "not found"})


@pytest.fixture
def dashboard() -> FakeDashboard:
    return FakeDashboard()


@pytest.fixture
def client(dashboard: FakeDashboard) -> ShipwrightsClient:
    return ShipwrightsClient(
        base_url="https://ds.shipwrights.dev",
        session_cookie="test-jwt",
        transport=httpx.MockTransport(dashboard.handler),
    )
