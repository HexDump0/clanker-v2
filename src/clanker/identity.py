"""Who is calling the extension API.

The extension sends the caller's Dashboard session token. The API first *validates* it against the
Dashboard (a live session). Only then does it read the claims inside the same token, which is safe
because the Dashboard accepted it. We keep the user's id, display name and Slack handle, never the
email or the token itself.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Identity:
    id: str
    name: str
    slack_id: str = ""
    slack_username: str = ""

    def matches(self, allowed: set[str]) -> bool:
        """True if any of this person's identifiers is in the (lowercased) allow-list."""
        handles = {self.id, self.slack_id, self.slack_username, self.name}
        return any(h.lower() in allowed for h in handles if h)


def _claims(token: str) -> dict | None:
    """The token's payload, UNVERIFIED. Only trust it after the Dashboard accepted the token."""
    try:
        payload = token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def token_expired(token: str, now: float | None = None) -> bool:
    """True when the token's own expiry has passed (no need to ask the Dashboard)."""
    exp = (_claims(token) or {}).get("exp")
    return isinstance(exp, (int, float)) and exp < (time.time() if now is None else now)


def identity_from_token(token: str) -> Identity | None:
    user = (_claims(token) or {}).get("user")
    if not isinstance(user, dict) or not user.get("id"):
        return None
    slack_username = str(user.get("slackUsername") or "")
    return Identity(
        id=str(user["id"]),
        name=str(user.get("displayName") or slack_username or user["id"]),
        slack_id=str(user.get("slackId") or ""),
        slack_username=slack_username,
    )
