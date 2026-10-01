"""Daily review budget for browser-extension requests (each review costs real money).

Counts per user and overall, per UTC day, saved to a small JSON file so a restart does not hand
everyone a fresh budget. A limit of 0 means unlimited.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path


def _utc_day() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


class UsageLimiter:
    def __init__(
        self,
        path: Path | None,
        *,
        per_user: int,
        per_day: int,
        today: Callable[[], str] = _utc_day,
    ) -> None:
        self._path = path
        self._per_user = per_user
        self._per_day = per_day
        self._today = today
        self._day = today()
        self._total = 0
        self._users: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if self._path is None:
            return
        try:
            data = json.loads(self._path.read_text())
        except (OSError, ValueError):
            return
        if data.get("day") == self._day:
            self._total = int(data.get("total", 0))
            self._users = {str(k): int(v) for k, v in data.get("users", {}).items()}

    def _save(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"day": self._day, "total": self._total, "users": self._users})
            )
            os.replace(tmp, self._path)
        except OSError:
            pass  # the limit still holds in memory

    def _roll(self) -> None:
        if (day := self._today()) != self._day:
            self._day, self._total, self._users = day, 0, {}

    def left(self, user_id: str) -> int | None:
        """Reviews this user can still request today (None = unlimited)."""
        self._roll()
        options = []
        if self._per_user:
            options.append(self._per_user - self._users.get(user_id, 0))
        if self._per_day:
            options.append(self._per_day - self._total)
        return max(0, min(options)) if options else None

    def try_use(self, user_id: str) -> str | None:
        """Spend one review. Returns an error message when over budget, else None."""
        self._roll()
        if self._per_user and self._users.get(user_id, 0) >= self._per_user:
            return f"You've used your {self._per_user} reviews for today. Try again tomorrow."
        if self._per_day and self._total >= self._per_day:
            return "Clanker has hit its daily review limit. Try again tomorrow."
        self._users[user_id] = self._users.get(user_id, 0) + 1
        self._total += 1
        self._save()
        return None
