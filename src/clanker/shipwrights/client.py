"""Async client for the Shipwrights Dashboard API.

Authenticates with the dashboard session cookie (a JWT) and talks to
``/api/v1/workplaces/{slug}/...`` directly — no community-dash proxy in between.

Mutating endpoints (claim, submit review, internal notes) exist on the API and are
implemented here, but the client refuses to call them unless constructed with
``allow_mutations=True``. The watcher and any read-only tooling never set it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import TracebackType
from typing import Any, Self

import httpx

from clanker.config import Settings
from clanker.shipwrights.models import (
    CertDetail,
    CertificationPage,
    CertStatus,
    CertSummary,
    GitHubData,
    LeaderboardEntry,
    Verdict,
)

USER_AGENT = "clanker/0.1 (+https://github.com/hackclub)"
DEFAULT_TIMEOUT = 30.0


class ShipwrightsError(Exception):
    """The API returned an unexpected response."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class AuthenticationError(ShipwrightsError):
    """Session cookie missing, expired, or lacking permission (401/403)."""


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
        if not session_cookie:
            raise AuthenticationError(401, "session cookie is empty")
        self.workplace = workplace
        self.allow_mutations = allow_mutations
        self._http = httpx.AsyncClient(
            transport=transport,
            base_url=base_url.rstrip("/") + "/api/v1",
            cookies={"session": session_cookie},
            headers={"accept": "application/json", "user-agent": USER_AGENT},
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

        if response.is_redirect:
            # The dashboard redirects unauthenticated requests to the login page.
            raise AuthenticationError(
                response.status_code,
                f"redirected to {response.headers.get('location')} — session cookie "
                "likely expired",
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
    ) -> CertificationPage:
        """One page of certifications (the server returns ~50 per page)."""
        params: dict[str, Any] = {"page": page}
        if status is not None:
            params["status"] = status.value
        if query:
            params["q"] = query
        if ai_type:
            params["aiType"] = ai_type
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
        return GitHubData.model_validate(data.get("data") or {})

    async def get_readme(self, cert_id: str) -> str:
        """Server-side cached README markdown for a cert."""
        data = await self._request("GET", self._wp(f"/certifications/{cert_id}/readme"))
        return data.get("markdown") or ""

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
