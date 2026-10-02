"""Keeps every result's "what has a human done with this ship" state fresh.

Clanker's queue is the set of ships a human still has to act on. That is not Clanker's
verdict — a reject, an approve and a needs-human all stay in the queue — it is whether
Stardance still lists the ship as waiting. So this reads the two admin pages the watcher
already uses (same host, same session, no Dashboard traffic):

- ``/admin/certification/ship?status=pending`` — the ships waiting right now.
- ``/admin/certification/ship/logs`` — one row per *reviewed* ship, with the outcome
  (``approved`` / ``returned``), who reviewed it, when, and their feedback.

The two are disjoint (a ship that is waiting has not been reviewed; a reviewed ship is no
longer waiting), so together they describe every ship:

===============================  ================================
in the pending queue             in the Clanker queue (still open)
in the review log, not waiting   decided — leaves the queue
in neither                       untouched — stays in the queue
in both                          resubmitted after a return — back in the queue
===============================  ================================

Triggered on demand by ``GET /api/results`` rather than by a timer, so an idle bot makes no
requests at all: ``maybe_refresh`` runs one bounded pass when the extension reads the list
and the last pass is older than ``interval``. Concurrent readers share a single pass.

The review log is kept in a local cache (``ReviewLogCache``). It only ever grows — one
immutable row per reviewed ship — so caching it is what makes everything else cheap: a ship's
review is normally already local, and a page of 50 rows normally covers everything new. An
update fetches the newest page and stops when it added nothing new; if the page only partly
overlapped what we hold it takes the next page too, until the cache is contiguous again.
Cache updates also run on a timer (30 min by default) so it stays warm without anyone
watching.

A state pass itself is **one request**: the waiting set. Settled ships and ships still waiting
are answered by it, and the rest come from the cache; only a cache miss costs a lookup.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from clanker.results import ResultRecord, ResultStore, ship_id_of
from clanker.stardance import ReviewLogEntry, StardanceAdminClient, parse_relative_when

logger = logging.getLogger(__name__)

# How many ships we look up one-by-one in a single pass. This bounds the tail, not the common
# case: most passes only read the waiting set.
DEFAULT_BACKFILL_LIMIT = 40
# How many review-log lookups run at once. A handful keeps a boot sweep quick without looking
# like a crawl from Stardance's side.
LOOKUP_CONCURRENCY = 5


def _chunks(items: list[str], size: int = LOOKUP_CONCURRENCY) -> Iterator[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class CachedReview(BaseModel):
    """One review-log row as cached locally. The log is append-only and holds one row per
    ship, so an entry never changes once read."""

    decision: str
    reviewed_by: str = ""
    reviewed_at: str | None = None
    review_note: str = ""


class ReviewLogCache:
    """A local copy of Stardance's review log.

    The log only ever grows (one immutable row per reviewed ship), so keeping it is what makes
    the rest cheap: a ship's review is normally already here, and only a miss costs a request.
    Persisted so a restart does not start cold.
    """

    def __init__(self, path: Path | None, *, max_entries: int = 20000) -> None:
        # No path means an in-memory cache (tests, or a deployment that does not want one):
        # it still answers lookups, it just does not survive a restart.
        self._path = path
        self._max_entries = max_entries
        self.entries: dict[str, CachedReview] = {}
        self.newest_ship_id: str = ""  # the frontier: the highest ship id ever seen
        self.updated_at: str | None = None

    @property
    def size(self) -> int:
        return len(self.entries)

    @property
    def is_empty(self) -> bool:
        return not self.entries

    def load(self) -> None:
        """Read the cache, tolerating a missing or corrupt file (we would just refill it)."""
        if self._path is None:
            return
        try:
            raw = json.loads(self._path.read_text())
        except (FileNotFoundError, ValueError, OSError):
            return
        self.newest_ship_id = str(raw.get("newest_ship_id") or "")
        self.updated_at = raw.get("updated_at")
        entries = raw.get("entries")
        if isinstance(entries, dict):
            self.entries = {
                str(k): CachedReview.model_validate(v)
                for k, v in entries.items()
                if isinstance(v, dict)
            }

    def save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "newest_ship_id": self.newest_ship_id,
            "updated_at": self.updated_at or datetime.now(UTC).isoformat(),
            "entries": {k: v.model_dump(mode="json") for k, v in self.entries.items()},
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False))
        tmp.replace(self._path)

    def merge(self, entries: list[ReviewLogEntry], *, now: datetime | None = None) -> int:
        """Add rows we have not seen; returns how many were new."""
        added = 0
        for entry in entries:
            if entry.ship_id in self.entries:
                continue
            self.entries[entry.ship_id] = CachedReview(
                decision=entry.decision,
                reviewed_by=entry.reviewed_by,
                reviewed_at=parse_relative_when(entry.when_text, now=now),
                review_note=entry.feedback,
            )
            added += 1
            if not self.newest_ship_id or int(entry.ship_id) > int(self.newest_ship_id):
                self.newest_ship_id = entry.ship_id
        if added:
            self._prune()
            self.updated_at = (now or datetime.now(UTC)).isoformat()
        return added

    def _prune(self) -> None:
        """Keep the newest entries; the cache is only ever read for recent ships."""
        excess = len(self.entries) - self._max_entries
        if excess <= 0:
            return
        oldest = sorted(self.entries, key=int)[:excess]
        for ship_id in oldest:
            del self.entries[ship_id]

    def get(self, ship_id: str) -> CachedReview | None:
        return self.entries.get(ship_id)


@dataclass(slots=True)
class RefreshSummary:
    """What one pass did, for logging and tests."""

    checked: int = 0
    changed: int = 0
    decided: int = 0
    waiting: int = 0
    lookups: int = 0
    requests: int = 0
    cache_added: int = 0
    error: str | None = None

    def __str__(self) -> str:
        if self.error:
            return f"error: {self.error}"
        return (
            f"{self.checked} tracked, {self.changed} changed "
            f"({self.decided} decided, {self.waiting} waiting), "
            f"{self.lookups} per-ship lookups"
        )


@dataclass(slots=True)
class CacheSummary:
    """What one review-log cache update did."""

    added: int = 0
    pages: int = 0
    total: int = 0
    error: str | None = None

    def __str__(self) -> str:
        if self.error:
            return f"error: {self.error}"
        return f"{self.added} new reviews, {self.pages} page(s), {self.total} cached"


class StatusRefresher:
    """Reads Stardance's queue and its review log to fill in each result's review state."""

    def __init__(
        self,
        admin: StardanceAdminClient,
        store: ResultStore,
        *,
        cache: ReviewLogCache | None = None,
        interval: float = 300.0,
        log_limit: int = 50,
        cache_max_pages: int = 4,
        cache_interval: float = 1800.0,
        startup_pages: int = 20,
        backfill_limit: int = DEFAULT_BACKFILL_LIMIT,
        max_lookups: int = 200,
    ) -> None:
        self._admin = admin
        self._store = store
        self.cache = cache if cache is not None else ReviewLogCache(None)
        self.interval = interval
        self._log_limit = log_limit
        self._cache_max_pages = cache_max_pages
        self.cache_interval = cache_interval
        self._startup_pages = startup_pages
        self._backfill_limit = backfill_limit
        self._max_lookups = max_lookups
        self._lock = asyncio.Lock()
        self._last_pass = 0.0
        self._last_cache_sync = 0.0
        self.last_error: str | None = None

    @property
    def seconds_since_pass(self) -> float | None:
        return None if not self._last_pass else time.monotonic() - self._last_pass

    @property
    def seconds_since_cache_sync(self) -> float | None:
        return None if not self._last_cache_sync else time.monotonic() - self._last_cache_sync

    async def aclose(self) -> None:
        await self._admin.aclose()

    async def maybe_refresh(self) -> RefreshSummary | None:
        """Run a pass if one is due. Returns None when it skipped."""
        if self.seconds_since_pass is not None and self.seconds_since_pass < self.interval:
            return None
        async with self._lock:
            # Another reader may have refreshed while we waited for the lock.
            again = self.seconds_since_pass
            if again is not None and again < self.interval:
                return None
            try:
                await self.sync_cache()
                summary = await self.refresh()
            except Exception as exc:
                # A failure must not fail the caller's request: the extension still gets the
                # last known states, just older.
                logger.warning("Could not refresh ship review states: %s", exc, exc_info=True)
                summary = RefreshSummary(error=str(exc) or type(exc).__name__)
            self.last_error = summary.error
            # Record the attempt either way, so a broken session cannot turn into a hot loop.
            self._last_pass = time.monotonic()
            return summary

    async def reconcile(self) -> RefreshSummary | None:
        """A background pass. Shares the lock, so an on-demand reader never doubles the work."""
        async with self._lock:
            try:
                summary = await self.refresh()
            except Exception as exc:
                logger.warning("Could not reconcile ship review states: %s", exc, exc_info=True)
                summary = RefreshSummary(error=str(exc) or type(exc).__name__)
            self.last_error = summary.error
            self._last_pass = time.monotonic()
            return summary

    async def startup_sweep(self) -> tuple[CacheSummary, RefreshSummary]:
        """Reconcile everything after a restart, before anyone asks.

        Ships can be approved or returned while the bot is down, and a cold cache knows nothing,
        so a boot pulls further into the log than usual and then re-checks *every* tracked ship
        it could not answer from the cache — including queue members that should now move out.
        """
        async with self._lock:
            cache = await self.sync_cache(force=True, max_pages=self._startup_pages)
            try:
                summary = await self.refresh(backfill_limit=self._max_lookups)
            except Exception as exc:
                # Same contract as an on-demand pass: report it, keep the last known states.
                logger.warning("Startup sweep could not read ship states: %s", exc, exc_info=True)
                summary = RefreshSummary(error=str(exc) or type(exc).__name__)
            self._last_pass = time.monotonic()
            self.last_error = summary.error or cache.error
            logger.info("Startup sweep: %s | %s", cache, summary)
            return cache, summary

    async def sync_cache(
        self, *, interval: float = 0.0, force: bool = False, max_pages: int | None = None
    ) -> CacheSummary:
        """Bring the local review-log copy up to date, if one is due.

        Fetches the newest page. If it brought nothing new, or every row on it was already
        cached, we are up to date and stop — that is the steady state, one request. If the page
        only partly overlapped, fewer than ``log_limit`` reviews happened since we last looked,
        so there may be rows between what we hold and what we just fetched: take the next page
        and merge, until a page adds nothing we did not already have (everything from here down
        is older than what we hold) or ``cache_max_pages`` is reached.
        """
        since = self.seconds_since_cache_sync
        if not force and since is not None and since < interval:
            return CacheSummary(total=self.cache.size)
        summary = CacheSummary()
        try:
            for page in range(1, (max_pages or self._cache_max_pages) + 1):
                entries = await self._admin.review_log(limit=self._log_limit, page=page)
                summary.pages += 1
                added = self.cache.merge(entries)
                summary.added += added
                if not entries or added == 0:
                    break  # fully caught up (or the log is empty)
                if len(entries) < self._log_limit:
                    break  # a short page is the end of the log
        except Exception as exc:
            summary.error = str(exc) or type(exc).__name__
            logger.warning("Could not update the review-log cache: %s", exc, exc_info=True)
        self._last_cache_sync = time.monotonic()
        if not summary.error:
            self.cache.save()
            summary.total = self.cache.size
        logger.info("Review-log cache: %s", summary)
        return summary

    async def refresh(self, *, backfill_limit: int | None = None) -> RefreshSummary:
        """One pass: read the waiting set, then resolve from the cache (and a few lookups).

        The waiting set is one request and answers most of the question. The review log is read
        from the local cache, so a ship whose review we have already seen costs nothing. A
        review-log request happens only for a ship that is not waiting, that we have no cached
        review for, and that could have moved since we last looked.
        """
        if backfill_limit is None:
            backfill_limit = self._backfill_limit
        summary = RefreshSummary()
        records = self._store.list()
        summary.checked = len(records)
        if not records:
            return summary

        # ship id -> record, for the ids we can resolve at all.
        by_ship: dict[str, ResultRecord] = {}
        for record in records:
            ship_id = ship_id_of(record.stardance_url)
            if ship_id:
                by_ship[ship_id] = record
        if not by_ship:
            return summary

        waiting = await self._admin.pending_ship_ids()
        summary.requests += 1
        summary.waiting = sum(1 for ship_id in by_ship if ship_id in waiting)

        # Only ships that are not waiting can be in the review log, and then only those we have
        # no cached review for (a cached one cannot have changed, and a ship we thought was
        # waiting has just been reviewed, so re-read it). A settled ship, or one still waiting,
        # costs nothing.
        needs: list[str] = [
            ship_id
            for ship_id, record in by_ship.items()
            if ship_id not in waiting
            and self.cache.get(ship_id) is None
            and (record.decision is None or record.waiting)
        ]

        found: dict[str, CachedReview] = {}
        if needs:
            # Lookups run a few at a time: a boot sweep can have ~90 cold ships to resolve and
            # serial requests would hold the extension's first page load for a minute.
            semaphore = asyncio.Semaphore(LOOKUP_CONCURRENCY)

            async def lookup(ship_id: str) -> None:
                async with semaphore:
                    summary.lookups += 1
                    summary.requests += 1
                    try:
                        entries = await self._admin.review_log(search=ship_id)
                    except Exception:
                        logger.warning(
                            "Review-log lookup failed for ship %s", ship_id, exc_info=True
                        )
                        return
                    for entry in entries:
                        if entry.ship_id == ship_id:
                            summary.cache_added += self.cache.merge([entry])
                            found[ship_id] = self.cache.get(ship_id) or CachedReview(
                                entry.decision
                            )
                            return

            for chunk in _chunks(needs[: min(backfill_limit, self._max_lookups)]):
                await asyncio.gather(*(lookup(ship_id) for ship_id in chunk))

        for ship_id, record in by_ship.items():
            cached = found.get(ship_id) or self.cache.get(ship_id)
            decision = cached.decision if cached else record.decision
            is_waiting = ship_id in waiting
            if decision is not None:
                summary.decided += 1
            before = (record.decision, record.waiting, record.reviewed_by, record.review_note)
            updated = self._store.set_review_state(
                record.cert_id,
                decision=decision,
                waiting=is_waiting,
                reviewed_by=cached.reviewed_by if cached else None,
                reviewed_at=cached.reviewed_at if cached else None,
                review_note=cached.review_note or None if cached else None,
            )
            if updated is not None and before != (
                updated.decision,
                updated.waiting,
                updated.reviewed_by,
                updated.review_note,
            ):
                summary.changed += 1

        logger.info("Ship review states: %s", summary)
        return summary
