"""Stardance admin queue client — the alternate watcher source.

The Shipwrights Dashboard's Stardance import has been lagging (journal
2026-08-30), while Stardance itself is the source of truth for ships. This
module scrapes the admin ship-queue page (HTML, no JSON API — ``.json`` and
``format=json`` both 500) so the watcher can detect new pending ships there
and reconcile them against Dashboard certs by ``external_id``.

Markup contract (verified live 2026-08-30):

- The page carries a metrics block (``ship-queue__label`` /
  ``ship-queue__metric-value``) whose ``In queue`` value is the pending total.
- Ships are ``<tr class="ship-queue__row...">`` rows sorted newest-first:
  ``ship-queue__project-title``, ``ship-queue__project-id`` (``#123``),
  ``ship-queue__cell-author`` (bare text), a ``ship-queue__wait-badge``,
  ``ship-queue__hours``, and a ``status-pill status-pill--<status>`` cell.
  Some spans are duplicated for responsive layouts; the parser keeps the
  first occurrence per field.
- The page also links the "oldest waiting" ship inside a metric tile; that
  link must not be mistaken for a queue row, hence row-scoped parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

STARDANCE_BASE_URL = "https://stardance.hackclub.com"
STARDANCE_COOKIE_NAME = "_stardance_session_4"
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TIMEOUT = 20.0

_ROW_CLASS = "ship-queue__row"
_IN_QUEUE_RE = re.compile(
    r"ship-queue__label\">\s*In queue\s*</span>.*?"
    r"ship-queue__metric-value[^>]*>\s*([\d,]+)",
    re.S,
)
_PROJECT_ID_RE = re.compile(r"#(\d+)")

# span class fragment -> field name; first hit per field wins.
_SPAN_FIELDS = (
    ("ship-queue__project-title", "title"),
    ("ship-queue__project-id", "ship_id"),
    ("ship-queue__wait-badge", "wait"),
    ("ship-queue__hours", "hours"),
    ("ship-queue__type-tag", "project_type"),
)


class StardanceAdminError(RuntimeError):
    """The admin queue page could not be fetched or parsed."""


@dataclass(frozen=True, slots=True)
class AdminShip:
    ship_id: str
    title: str
    author: str
    status: str
    wait: str = ""
    hours: str = ""
    project_type: str = ""
    demo_url: str = ""
    repo_url: str = ""


@dataclass(frozen=True, slots=True)
class AdminQueuePage:
    total: int
    page: int
    ships: list[AdminShip]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class _QueueTableParser(HTMLParser):
    """Extract ship rows (and per-row fields) from the admin queue table."""

    def __init__(self) -> None:
        super().__init__()
        self.ships: list[AdminShip] = []
        self._in_row = False
        self._cell_class: str | None = None
        self._field: str | None = None
        self._buf: list[str] = []
        self._current: dict[str, str] = {}
        self._seen: set[str] = set()
        self._link: tuple[str, list[str]] | None = None  # (href, label chars)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = dict(attrs).get("class") or ""
        if tag == "tr":
            self._in_row = _ROW_CLASS in classes.split()
            if self._in_row:
                self._current, self._seen = {}, set()
            return
        if not self._in_row:
            return
        if tag == "td":
            self._cell_class = classes
            return
        if tag == "a" and "ship-queue__quick-link" in classes:
            self._link = (dict(attrs).get("href") or "", [])
            return
        if tag == "span" and self._field is None:
            for fragment, field in _SPAN_FIELDS:
                if fragment in classes and field not in self._seen:
                    self._field, self._buf = field, []
                    return
            if "status-pill--" in classes and "status" not in self._seen:
                self._current["status"] = classes.split("status-pill--", 1)[1].split()[0]
                self._seen.add("status")

    def handle_data(self, data: str) -> None:
        if not self._in_row:
            return
        if self._link is not None:
            self._link[1].append(data)
        elif self._field is not None:
            self._buf.append(data)
        elif (
            self._cell_class is not None
            and "ship-queue__cell-author" in self._cell_class
            and "author" not in self._seen
        ):
            self._current["author"] = _clean(data)
            self._seen.add("author")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._link is not None:
            href, label = self._link
            self._link = None
            label = _clean("".join(label)).lower()
            if href:
                if label.startswith("demo"):
                    self._current["demo_url"] = href
                elif label.startswith("repo"):
                    self._current["repo_url"] = href
        elif tag == "span" and self._field is not None:
            self._current[self._field] = _clean("".join(self._buf))
            self._seen.add(self._field)
            self._field = None
        elif tag == "td":
            self._cell_class = None
        elif tag == "tr" and self._in_row:
            self._in_row = False
            ship_id = _PROJECT_ID_RE.sub(r"\1", self._current.get("ship_id", ""))
            if ship_id:
                self.ships.append(
                    AdminShip(
                        ship_id=ship_id,
                        title=self._current.get("title", ""),
                        author=self._current.get("author", ""),
                        status=self._current.get("status", ""),
                        wait=self._current.get("wait", ""),
                        hours=self._current.get("hours", ""),
                        project_type=self._current.get("project_type", ""),
                        demo_url=self._current.get("demo_url", ""),
                        repo_url=self._current.get("repo_url", ""),
                    )
                )


def parse_queue(html: str, *, page: int = 1) -> AdminQueuePage:
    """Parse one admin queue page into its total and ship rows."""
    parser = _QueueTableParser()
    parser.feed(html)
    parser.close()
    m = _IN_QUEUE_RE.search(html)
    if m is None:
        raise StardanceAdminError("In queue metric not found — page markup changed?")
    total = int(m.group(1).replace(",", ""))
    return AdminQueuePage(total=total, page=page, ships=parser.ships)


def normalize_session(raw: str) -> str:
    """Accept a bare cookie value or a pasted ``_stardance_session_4=...`` pair."""
    value = raw.strip().rstrip(";").strip()
    return value.removeprefix(f"{STARDANCE_COOKIE_NAME}=").strip()


def parse_dash_cert_id(redirect_location: str) -> str:
    """Extract the Dashboard cert id from a ship-page redirect target.

    The admin ship page 302s to e.g.
    ``https://ds.shipwrights.dev/stardance/certifications/<uuid>`` once the
    Dashboard knows the ship; the cert id is the last path segment.
    """
    return urlparse(redirect_location).path.rstrip("/").rsplit("/", 1)[-1]


class StardanceAdminClient:
    """Read-only access to the Stardance admin ship queue."""

    def __init__(self, session: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._session = normalize_session(session)
        self._http = httpx.AsyncClient(
            base_url=STARDANCE_BASE_URL,
            timeout=TIMEOUT,
            headers=BROWSER_HEADERS,
            follow_redirects=False,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def queue_page(self, *, page: int = 1, status: str = "pending") -> AdminQueuePage:
        """One page of the admin ship queue (25 rows), newest first."""
        response = await self._http.get(
            "/admin/certification/ship",
            params={
                "status": status,
                "sort": "newest",
                "from": "",
                "to": "",
                "project_type": "",
                "search": "",
                "page": page,
            },
            # Per-request Cookie header (not ``cookies=``): keeps the session
            # off the shared client and out of any redirect cross-origin leak
            # (redirects are not followed; journal 2026-08-29-12).
            headers={"Cookie": f"{STARDANCE_COOKIE_NAME}={self._session}"},
        )
        if response.is_redirect:
            raise StardanceAdminError(
                "admin queue redirected (to "
                f"{response.headers.get('location', '?')}) — session cookie "
                "likely expired",
            )
        if response.status_code >= 400:
            raise StardanceAdminError(
                f"admin queue returned HTTP {response.status_code}",
            )
        return parse_queue(response.text, page=page)

    async def ship_redirect_target(self, ship_id: str) -> str | None:
        """Probe one admin ship page for a Dashboard redirect.

        Once the Shipwrights Dashboard has imported a ship, its admin page
        302s to the Dashboard certification URL (whose last path segment is
        the cert id). Ships the Dashboard does not know render the Stardance
        review page with HTTP 200.

        Returns the redirect target, or None when there is no redirect. A
        redirect back to Stardance's login means the session cookie expired.
        """
        response = await self._http.get(
            f"/admin/certification/ship/{ship_id}",
            headers={"Cookie": f"{STARDANCE_COOKIE_NAME}={self._session}"},
        )
        if response.is_redirect:
            location = response.headers.get("location") or ""
            if "shipwrights" in urlparse(location).netloc:
                return location
            raise StardanceAdminError(
                f"ship page redirected to {location or '?'} — session cookie likely expired",
            )
        if response.status_code >= 400:
            raise StardanceAdminError(
                f"ship page for {ship_id} returned HTTP {response.status_code}",
            )
        return None
