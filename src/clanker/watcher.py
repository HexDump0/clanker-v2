"""Watch the Shipwrights queue for new pending certifications.

Replaces v1's community-dash poller. Differences that matter:

- Talks to the real dashboard API (all PENDING pages, not a proxy's top-N).
- Seen-cert state is persisted to disk, so a restart neither re-announces old
  certs nor silently skips ships submitted while the watcher was down.
- Emits new certs through a callback — no Slack or review logic in here.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from clanker.shipwrights import CertStatus, CertSummary, ShipwrightsClient

logger = logging.getLogger(__name__)

STATE_VERSION = 1

NewCertHandler = Callable[[CertSummary], Awaitable[None]]


@dataclass
class WatcherState:
    seen_ids: set[str] = field(default_factory=set)
    last_poll_at: str | None = None

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
        )

    def save(self, path: Path) -> None:
        """Atomically persist state (write to a temp file, then rename)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": STATE_VERSION,
            "seen_ids": sorted(self.seen_ids),
            "last_poll_at": self.last_poll_at,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)


# Even when nothing seems to have changed, re-walk the whole queue every N polls
# in case a change slipped past the cheap fingerprint (e.g. one cert added and
# another claimed within the same interval, leaving the total unchanged).
FULL_SWEEP_EVERY = 20


class Watcher:
    """Polls PENDING certifications and hands new ones to a handler.

    ``emit_backlog`` controls the very first run (no state file): False records
    the existing queue without emitting; True treats the whole backlog as new.

    Most polls cost a single request: page 1 carries the queue total, and the
    full multi-page walk only happens when the (total, page-1 ids) fingerprint
    changes — or every ``FULL_SWEEP_EVERY`` polls as a safety net.
    """

    def __init__(
        self,
        client: ShipwrightsClient,
        *,
        state_file: Path,
        poll_interval: float = 30.0,
        emit_backlog: bool = False,
    ) -> None:
        self._client = client
        self._state_file = state_file
        self._poll_interval = poll_interval
        self._emit_backlog = emit_backlog
        loaded = WatcherState.load(state_file)
        self._first_run = loaded is None
        self._state = loaded or WatcherState()
        self._last_fingerprint: tuple[int, frozenset[str]] | None = None
        self._polls_since_walk = 0

    async def poll_once(self) -> list[CertSummary]:
        """Check the pending queue and return certs not seen before.

        Seen-state is updated and persisted; deciding what to do with the new
        certs is the caller's job.
        """
        first_page = await self._client.list_certifications(status=CertStatus.PENDING, page=1)
        fingerprint = (first_page.total, frozenset(c.id for c in first_page.certs))

        unchanged = fingerprint == self._last_fingerprint
        if unchanged and not self._first_run and self._polls_since_walk < FULL_SWEEP_EVERY:
            self._polls_since_walk += 1
            return []

        pending = list(first_page.certs)
        for page in range(2, first_page.pages + 1):
            result = await self._client.list_certifications(
                status=CertStatus.PENDING, page=page
            )
            if not result.certs:
                break
            pending.extend(result.certs)
        self._last_fingerprint = fingerprint
        self._polls_since_walk = 0

        fresh = [c for c in pending if c.id not in self._state.seen_ids]
        self._state.seen_ids.update(c.id for c in pending)
        self._state.last_poll_at = datetime.now(UTC).isoformat()
        self._state.save(self._state_file)

        if self._first_run:
            self._first_run = False
            if not self._emit_backlog:
                logger.info(
                    "First run: recorded %d existing pending certs without emitting",
                    len(pending),
                )
                return []
        return fresh

    async def run(self, on_new_cert: NewCertHandler) -> None:
        """Poll forever, invoking ``on_new_cert`` for each newly seen cert.

        A failure in one poll (network, auth, handler) is logged and the loop
        keeps going.
        """
        logger.info(
            "Watching %s for new pending certs every %.0fs (state: %s)",
            self._client.workplace,
            self._poll_interval,
            self._state_file,
        )
        while True:
            try:
                for cert in await self.poll_once():
                    logger.info(
                        "New cert %s: %r by %s",
                        cert.id,
                        cert.project_name,
                        cert.submitter_username or cert.submitter_slack_id,
                    )
                    try:
                        await on_new_cert(cert)
                    except Exception:
                        logger.exception("Handler failed for cert %s", cert.id)
            except Exception:
                logger.exception("Poll failed")
            await asyncio.sleep(self._poll_interval)
