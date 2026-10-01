"""Async client for the Shipwrights Dashboard API.

Authenticates with the dashboard session cookie (a JWT) and talks to
``/api/v1/workplaces/{slug}/...`` directly — no community-dash proxy in between.

Mutating endpoints (claim, submit review, internal notes) exist on the API and are
implemented here, but the client refuses to call them unless constructed with
``allow_mutations=True``. The watcher and any read-only tooling never set it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from http.cookies import SimpleCookie
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import httpx

from clanker.config import Settings
from clanker.shipwrights.models import (
    CertDetail,
    CertificationPage,
    CertStatus,
    CertSummary,
    FeedbackTemplates,
    GitHubData,
    LeaderboardEntry,
    ReadmeData,
    Verdict,
)

DEFAULT_TIMEOUT = 30.0


class ShipwrightsError(Exception):
    """The API returned an unexpected response."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class AuthenticationError(ShipwrightsError):
    """Session cookie missing, expired, or lacking permission (401/403)."""


class CloudflareBlockError(ShipwrightsError):
    """Cloudflare rejected the request before Dashboard authentication."""


class NotFoundError(ShipwrightsError):
    """Unknown route or certification (404)."""


class MutationNotAllowedError(RuntimeError):
    """A mutating endpoint was called on a client without ``allow_mutations=True``."""

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"{operation} is a mutating operation; construct the client with "
            "allow_mutations=True to permit it"
        )


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict) and isinstance(body.get("error"), str):
            return body["error"]
    except ValueError:
        pass
    return response.text[:300]


def _is_cloudflare_block(response: httpx.Response) -> bool:
    if response.headers.get("cf-mitigated", "").lower() == "challenge":
        return True
    server = response.headers.get("server", "").lower()
    if "cloudflare" in server and response.status_code in {403, 429, 503}:
        return True
    body = response.text[:6000].lower()
    return any(
        marker in body
        for marker in (
            "attention required! | cloudflare",
            "sorry, you have been blocked",
            "/cdn-cgi/challenge-platform",
            "cf_chl_opt",
        )
    )


def _session_value(configured: str) -> str:
    """Accept a bare JWT, `session=...`, or a pasted Cookie header safely."""
    raw = configured.strip()
    if "=" not in raw:
        return raw
    cookies = SimpleCookie()
    try:
        cookies.load(raw)
    except Exception:
        return raw.removeprefix("session=").strip().rstrip(";")
    morsel = cookies.get("session")
    return morsel.value.strip() if morsel else raw.removeprefix("session=").strip().rstrip(";")


class ShipwrightsClient:
    """Typed client for one workplace on the Shipwrights Dashboard.

    Use as an async context manager so the underlying connection pool is reused
    and closed properly::

        async with ShipwrightsClient.from_settings(settings) as sw:
            page = await sw.list_certifications(status=CertStatus.PENDING)
    """

    def __init__(
        self,
        *,
        base_url: str,
        session_cookie: str,
        workplace: str = "stardance",
        allow_mutations: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        session_value = _session_value(session_cookie)
        if not session_value:
            raise AuthenticationError(401, "session cookie is empty")
        self.workplace = workplace
        self.allow_mutations = allow_mutations
        self._http = httpx.AsyncClient(
            transport=transport,
            base_url=base_url.rstrip("/") + "/api/v1",
            cookies={"session": session_value},
            # The old identifying `clanker/0.1` user agent is specifically
            # blocked by the Dashboard's Cloudflare policy. Ordinary HTTPX and
            # curl clients work, so keep HTTPX's default UA and request JSON-ish
            # content without pretending to be a browser.
            headers={"accept": "*/*", "accept-language": "en-US,en;q=0.9"},
            timeout=timeout,
            follow_redirects=False,
        )

    @classmethod
    def from_settings(cls, settings: Settings, *, allow_mutations: bool = False) -> Self:
        return cls(
            base_url=settings.shipwrights_base_url,
            session_cookie=settings.require_session(),
            workplace=settings.shipwrights_workplace,
            allow_mutations=allow_mutations,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ core

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        response = await self._http.request(method, path, params=params, json=json)

        if response.status_code >= 400 and _is_cloudflare_block(response):
            raise CloudflareBlockError(
                response.status_code,
                "Cloudflare blocked the Dashboard request before authentication",
            )
        if response.is_redirect:
            # The dashboard redirects unauthenticated requests to the login page.
            raise AuthenticationError(
                response.status_code,
                f"redirected to {response.headers.get('location')} — session cookie likely expired",
            )
        if response.status_code in (401, 403):
            raise AuthenticationError(response.status_code, _error_message(response))
        if response.status_code == 404:
            raise NotFoundError(404, _error_message(response))
        if response.status_code >= 400:
            raise ShipwrightsError(response.status_code, _error_message(response))
        return response.json()

    def _wp(self, path: str) -> str:
        return f"/workplaces/{self.workplace}{path}"

    def _require_mutations(self, operation: str) -> None:
        if not self.allow_mutations:
            raise MutationNotAllowedError(operation)

    # ------------------------------------------------------------- read-only

    async def list_certifications(
        self,
        *,
        status: CertStatus | None = None,
        page: int = 1,
        query: str | None = None,
        ai_type: str | None = None,
        sort: str | None = None,
    ) -> CertificationPage:
        """One page of certifications (the server returns ~50 per page).

        ``sort`` is a comma-separated table sort such as ``date:asc``.
        """
        params: dict[str, Any] = {"page": page}
        if status is not None:
            params["status"] = status.value
        if query:
            params["q"] = query
        if ai_type:
            params["aiType"] = ai_type
        if sort:
            params["sort"] = sort
        data = await self._request("GET", self._wp("/certifications"), params=params)
        return CertificationPage.model_validate(data)

    async def iter_certifications(
        self,
        *,
        status: CertStatus | None = None,
        query: str | None = None,
        ai_type: str | None = None,
    ) -> AsyncIterator[CertSummary]:
        """Every matching certification, walking all pages."""
        page = 1
        while True:
            result = await self.list_certifications(
                status=status, page=page, query=query, ai_type=ai_type
            )
            for cert in result.certs:
                yield cert
            if page >= result.pages or not result.certs:
                return
            page += 1

    async def get_certification(self, cert_id: str) -> CertDetail:
        data = await self._request("GET", self._wp(f"/certifications/{cert_id}"))
        return CertDetail.model_validate(data)

    async def get_github(self, cert_id: str) -> GitHubData:
        """Server-side cached GitHub repo + commits for a cert."""
        data = await self._request("GET", self._wp(f"/certifications/{cert_id}/github"))
        payload = dict(data.get("data") or {})
        payload.update(status=data.get("status"), cached=data.get("cached"))
        return GitHubData.model_validate(payload)

    async def get_readme_data(self, cert_id: str) -> ReadmeData:
        """Cached README plus freshness and error metadata."""
        data = await self._request("GET", self._wp(f"/certifications/{cert_id}/readme"))
        return ReadmeData.model_validate(data)

    async def get_readme(self, cert_id: str) -> str:
        """Cached README markdown (compatibility helper)."""
        return (await self.get_readme_data(cert_id)).markdown

    async def get_feedback_templates(self) -> FeedbackTemplates:
        """Shared and reviewer-owned canned feedback. Read-only."""
        data = await self._request("GET", self._wp("/feedback-templates"))
        return FeedbackTemplates.model_validate(data)

    async def get_leaderboard(self, range_: str = "weekly") -> list[LeaderboardEntry]:
        data = await self._request(
            "GET", self._wp("/certifications/leaderboard"), params={"range": range_}
        )
        return [LeaderboardEntry.model_validate(e) for e in data.get("entries", [])]

    async def get_workplace(self) -> dict[str, Any]:
        return await self._request("GET", self._wp(""))

    # -------------------------------------------------------------- mutating

    async def claim(self, cert_id: str, *, unclaim: bool = False) -> CertDetail:
        """Claim (or release) a cert: PENDING/RETURNED -> IN_REVIEW. [MUTATING]"""
        self._require_mutations("claim")
        data = await self._request(
            "POST",
            self._wp(f"/certifications/{cert_id}/claim"),
            json={"unclaim": unclaim},
        )
        return CertDetail.model_validate(data)

    async def submit_review(self, cert_id: str, verdict: Verdict, comment: str) -> Any:
        """Record a verdict. Requires the cert IN_REVIEW and us as claimer. [MUTATING]

        Stardance has ``feedbackRequired: true`` — an empty comment is rejected.
        """
        self._require_mutations("submit_review")
        if not comment.strip():
            raise ValueError("comment must be non-empty (feedbackRequired workplace)")
        return await self._request(
            "POST",
            self._wp(f"/certifications/{cert_id}/review"),
            json={"verdict": verdict.value, "comment": comment},
        )

    async def set_internal_notes(self, cert_id: str, notes: str) -> Any:
        """Update a cert's internal notes. [MUTATING]"""
        self._require_mutations("set_internal_notes")
        return await self._request(
            "PATCH",
            self._wp(f"/certifications/{cert_id}"),
            json={"internalNotes": notes},
        )

    async def upload_proof_video(self, cert_id: str, path: Path) -> str:
        """Upload a video to R2 and attach it to the cert; returns the public URL. [MUTATING]

        Three steps (see AI/context/API.md): presign, PUT the bytes, attach the URL.
        """
        self._require_mutations("upload_proof_video")
        presign = await self._request(
            "GET",
            self._wp(f"/certifications/{cert_id}/upload"),
            params={"filename": path.name, "contentType": "video/mp4"},
        )
        await self._put_video(presign["uploadUrl"], path)
        await self._request(
            "POST",
            self._wp(f"/certifications/{cert_id}/upload"),
            json={"url": presign["publicUrl"]},
        )
        return str(presign["publicUrl"])

    @staticmethod
    async def _put_video(upload_url: str, path: Path) -> None:
        """PUT the bytes to the presigned storage URL (not the Dashboard; no cookie)."""
        async with httpx.AsyncClient(timeout=300.0) as storage:
            response = await storage.put(
                upload_url, content=path.read_bytes(), headers={"Content-Type": "video/mp4"}
            )
            response.raise_for_status()
