"""Watch for new pending certifications.

Replaces v1's community-dash poller. Differences that matter:

- Seen-cert state is persisted to disk, so a restart neither re-announces old
  certs nor silently skips ships submitted while the watcher was down.
- Emits new certs through a callback — no Slack or review logic in here.
- Pluggable source: the Shipwrights Dashboard API (default) or the Stardance
  admin queue (the source of truth, useful while the Dashboard's Stardance
  import lags — see journal 2026-08-30).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from clanker.shipwrights import CertStatus, CertSummary, ShipwrightsClient
from clanker.stardance import (
    STARDANCE_BASE_URL,
    AdminQueuePage,
    AdminShip,
    StardanceAdminClient,
    StardanceAdminError,
    parse_dash_cert_id,
)

if TYPE_CHECKING:
    from clanker.config import Settings

logger = logging.getLogger(__name__)

STATE_VERSION = 1

# Even when nothing seems to have changed, re-walk the whole queue every N polls
# in case a change slipped past the cheap fingerprint (e.g. one cert added and
# another claimed within the same interval, leaving the total unchanged).
FULL_SWEEP_EVERY = 20

# The Stardance admin page serves 25 rows per page.
STARDANCE_PAGE_SIZE = 25

# When a newly detected ship is not yet on the Dashboard, wait this long and
# probe once more before declaring the Dashboard down (import can lag a few
# seconds behind Stardance).
DASH_PROBE_RETRY_DELAY = 10.0


@dataclass(frozen=True, slots=True)
class PendingEmission:
    """A ship the watcher hands to its handler.

    ``parent_ts`` is the Slack thread the ship was already announced in
    (Stardance flow announces at detection time); when None the handler
    announces first, as the Dashboard flow always has.
    """

    cert: CertSummary
    parent_ts: str | None = None


NewCertHandler = Callable[[PendingEmission], Awaitable[None]]


@dataclass
class WatcherState:
    seen_ids: set[str] = field(default_factory=set)
    last_poll_at: str | None = None
    source: str | None = None

    @classmethod
    def load(cls, path: Path) -> WatcherState | None:
        """Load persisted state, or None if there is none yet."""
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            logger.exception("Corrupt watcher state at %s — starting fresh", path)
            return None
        return cls(
            seen_ids=set(raw.get("seen_ids", [])),
            last_poll_at=raw.get("last_poll_at"),
            source=raw.get("source"),
        )

    def save(self, path: Path) -> None:
        """Atomically persist state (write to a temp file, then rename)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": STATE_VERSION,
            "seen_ids": sorted(self.seen_ids),
            "last_poll_at": self.last_poll_at,
            "source": self.source,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)


@dataclass(frozen=True, slots=True)
class PendingItem:
    """One pending ship as seen by a source.

    ``key`` is the source's stable identity (Dashboard cert id or Stardance
    ship id) used for fingerprinting and seen-state. ``summary`` is the fully
    reviewable Dashboard cert when the source can supply one.
    """

    key: str
    summary: CertSummary | None = None


@dataclass(frozen=True, slots=True)
class PendingPage:
    total: int
    page: int
    pages: int
    items: list[PendingItem]


class PendingSource(Protocol):
    """Where the watcher looks for pending ships.

    ``resolve`` turns newly-seen keys into reviewable emissions. It may return
    a subset (e.g. ships the Dashboard has not imported yet) and is called on
    every poll — including unchanged ones with an empty key list — so
    implementations can do deferred work.
    """

    name: str

    async def pending_page(self, page: int) -> PendingPage: ...

    async def resolve(self, keys: list[str]) -> list[PendingEmission]: ...


class ShipwrightsPendingSource:
    """The default source: the Shipwrights Dashboard certifications API."""

    name = "dashboard"

    def __init__(self, client: ShipwrightsClient) -> None:
        self._client = client
        self._summaries: dict[str, CertSummary] = {}

    async def pending_page(self, page: int) -> PendingPage:
        result = await self._client.list_certifications(status=CertStatus.PENDING, page=page)
        items = []
        for cert in result.certs:
            self._summaries[cert.id] = cert
            items.append(PendingItem(key=cert.id, summary=cert))
        return PendingPage(total=result.total, page=result.page, pages=result.pages, items=items)

    async def resolve(self, keys: list[str]) -> list[PendingEmission]:
        return [
            PendingEmission(cert=self._summaries[key]) for key in keys if key in self._summaries
        ]


class StardancePendingSource:
    """Watch the Stardance admin queue; resolve ships via the Dashboard.

    Announcement happens the instant a ship is detected, from Stardance data
    alone (title, author, type, demo/repo links; the Stardance admin ship page
    stands in for the Dashboard link). Resolution then probes that same admin
    ship page: once the Dashboard imports the ship, the page 302s to the
    Dashboard certification URL and the cert id falls out of it. A miss is
    retried once after ``probe_retry_delay`` seconds; a second miss is treated
    as "Dashboard down" — the ship is dropped (already marked seen) and the
    announcement thread gets a dash-crash note instead of a review.
    """

    name = "stardance"

    def __init__(
        self,
        admin: StardanceAdminClient,
        dashboard: ShipwrightsClient,
        *,
        announcer=None,  # Announcer | None; enables detection-time Slack messages
        probe_retry_delay: float = DASH_PROBE_RETRY_DELAY,
    ) -> None:
        self._admin = admin
        self._dashboard = dashboard
        self._announcer = announcer
        self._probe_retry_delay = probe_retry_delay
        self._ships: dict[str, AdminShip] = {}

    async def aclose(self) -> None:
        await self._admin.aclose()

    async def pending_page(self, page: int) -> PendingPage:
        result = await self._fetch(page)
        for ship in result.ships:
            self._ships[ship.ship_id] = ship
        items = [PendingItem(key=ship.ship_id) for ship in result.ships]
        pages = max(1, math.ceil(result.total / STARDANCE_PAGE_SIZE))
        return PendingPage(total=result.total, page=result.page, pages=pages, items=items)

    async def _fetch(self, page: int) -> AdminQueuePage:
        try:
            return await self._admin.queue_page(page=page)
        except Exception as exc:
            logger.error("Stardance admin queue fetch failed: %s", exc)
            raise

    def _ship_url(self, ship_id: str) -> str:
        return f"{STARDANCE_BASE_URL}/admin/certification/ship/{ship_id}"

    async def _probe_dash_cert_id(self, ship_id: str) -> str | None:
        """Probe the admin ship page; one retry after a short wait.

        Returns the Dashboard cert id once the ship redirects, or None after
        the second miss (Dashboard down / never imported).
        """
        target = await self._admin.ship_redirect_target(ship_id)
        if target is not None:
            return parse_dash_cert_id(target)
        if self._probe_retry_delay > 0:
            await asyncio.sleep(self._probe_retry_delay)
        target = await self._admin.ship_redirect_target(ship_id)
        return parse_dash_cert_id(target) if target is not None else None

    async def resolve(self, keys: list[str]) -> list[PendingEmission]:
        emissions: list[PendingEmission] = []
        for key in keys:
            ship = self._ships.pop(key, None)
            ship_url = self._ship_url(key)
            parent_ts: str | None = None
            if self._announcer is not None:
                view = ship or AdminShip(ship_id=key, title=key, author="", status="pending")
                try:
                    parent_ts = await self._announcer.announce_ship_from_stardance(
                        view, ship_url=ship_url
                    )
                except Exception:
                    logger.exception("Failed to announce Stardance ship %s", key)

            try:
                dash_cert_id = await self._probe_dash_cert_id(key)
            except StardanceAdminError as exc:
                logger.error("Stardance ship %s probe failed: %s", key, exc)
                dash_cert_id = None

            if dash_cert_id is None:
                logger.error(
                    "Stardance ship %s not imported by Dashboard — review skipped", key
                )
                if self._announcer is not None:
                    view = ship or AdminShip(ship_id=key, title=key, author="", status="pending")
                    await self._announcer.announce_dash_down(
                        view, ship_url=ship_url, parent_ts=parent_ts
                    )
                continue

            try:
                cert = await self._dashboard.get_certification(dash_cert_id)
            except Exception:
                logger.exception(
                    "Dashboard fetch failed for Stardance ship %s (cert %s)", key, dash_cert_id
                )
                if self._announcer is not None and parent_ts:
                    await self._announcer.post_failure(parent_ts)
                continue
            emissions.append(PendingEmission(cert=cert, parent_ts=parent_ts))
        return emissions


def make_pending_source(
    settings: Settings,
    client: ShipwrightsClient,
    *,
    announcer=None,  # Announcer | None; enables Stardance detection-time posts
) -> PendingSource:
    """Build the watcher source selected by ``settings.watcher_source``."""
    if settings.watcher_source == "stardance":
        admin = StardanceAdminClient(settings.stardance_session)
        return StardancePendingSource(admin, client, announcer=announcer)
    return ShipwrightsPendingSource(client)


class Watcher:
    """Polls a pending-ship source and hands new ones to a handler.

    ``emit_backlog`` controls the very first run (no state file): False records
    the existing queue without emitting; True treats the whole backlog as new.

    Most polls cost a single request: page 1 carries the queue total, and the
    full multi-page walk only happens when the (total, page-1 keys) fingerprint
    changes — or every ``FULL_SWEEP_EVERY`` polls as a safety net.
    """

    def __init__(
        self,
        source: PendingSource,
        *,
        state_file: Path,
        poll_interval: float = 30.0,
        emit_backlog: bool = False,
    ) -> None:
        self._source = source
        self._state_file = state_file
        self._poll_interval = poll_interval
        self._emit_backlog = emit_backlog
        loaded = WatcherState.load(state_file)
        # Seen-ids are source-namespaced (Dashboard cert ids vs Stardance ship
        # ids); switching sources restarts the watch without emitting a flood.
        self._first_run = loaded is None or loaded.source != source.name
        self._state = loaded if loaded is not None and not self._first_run else WatcherState(
            source=source.name
        )
        self._state.source = source.name
        self._last_fingerprint: tuple[int, frozenset[str]] | None = None
        self._polls_since_walk = 0

    async def poll_once(self) -> list[CertSummary]:
        """Check the pending queue and return certs not seen before.

        Seen-state is updated and persisted; deciding what to do with the new
        certs is the caller's job.
        """
        first_page = await self._source.pending_page(1)
        fingerprint = (first_page.total, frozenset(item.key for item in first_page.items))

        unchanged = fingerprint == self._last_fingerprint
        if unchanged and not self._first_run and self._polls_since_walk < FULL_SWEEP_EVERY:
            self._polls_since_walk += 1
            # No new keys, but the source may still have deferred work.
            return await self._source.resolve([])

        items = list(first_page.items)
        for page in range(2, first_page.pages + 1):
            result = await self._source.pending_page(page)
            if not result.items:
                break
            items.extend(result.items)
        self._last_fingerprint = fingerprint
        self._polls_since_walk = 0

        fresh_keys = list(
            dict.fromkeys(
                item.key for item in items if item.key not in self._state.seen_ids
            )
        )
        self._state.seen_ids.update(item.key for item in items)
        self._state.last_poll_at = datetime.now(UTC).isoformat()
        self._state.save(self._state_file)

        if self._first_run:
            self._first_run = False
            if not self._emit_backlog:
                logger.info(
                    "First run: recorded %d existing pending ships without emitting",
                    len(items),
                )
                return []
        return await self._source.resolve(fresh_keys)

    async def run(self, on_new_cert: NewCertHandler) -> None:
        """Poll forever, invoking ``on_new_cert`` for each newly seen cert.

        A failure in one poll (network, auth, handler) is logged and the loop
        keeps going.
        """
        logger.info(
            "Watching %s (source: %s) for new pending ships every %.0fs (state: %s)",
            STARDANCE_BASE_URL if self._source.name == "stardance" else "dashboard",
            self._source.name,
            self._poll_interval,
            self._state_file,
        )
        while True:
            try:
                for emission in await self.poll_once():
                    cert = emission.cert
                    logger.info(
                        "New cert %s: %r by %s",
                        cert.id,
                        cert.project_name,
                        cert.submitter_username or cert.submitter_slack_id,
                    )
                    try:
                        await on_new_cert(emission)
                    except Exception:
                        logger.exception("Handler failed for cert %s", cert.id)
            except Exception:
                logger.exception("Poll failed")
            await asyncio.sleep(self._poll_interval)
