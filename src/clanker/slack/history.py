"""Per-thread conversation history for the chat bot.

Two sources of history exist:

- :class:`ConversationStore` — an in-memory cache of pydantic-ai message logs
  keyed by thread, used as a fallback;
- :func:`fetch_thread_history` — reconstructs history directly from the Slack
  thread via ``conversations.replies`` so Clanker sees the *whole* thread even
  for messages posted before it was mentioned (and across restarts).
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)

ThreadKey = tuple[str, str, str]  # (team_id, channel_id, thread_ts)

_MENTION_RE = re.compile(r"<@([A-Z0-9]+)>")


class ConversationStore:
    """Thread-safe in-memory store for pydantic-ai message histories."""

    def __init__(self) -> None:
        self._store: dict[ThreadKey, list[ModelMessage]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: ThreadKey) -> list[ModelMessage]:
        async with self._lock:
            return list(self._store.get(key, []))

    async def save(self, key: ThreadKey, messages: list[ModelMessage]) -> None:
        async with self._lock:
            self._store[key] = list(messages)

    async def delete(self, key: ThreadKey) -> None:
        async with self._lock:
            self._store.pop(key, None)


class NameResolver:
    """Resolves Slack user IDs to display names, with an in-process cache."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def name(self, client: AsyncWebClient, user_id: str) -> str:
        if not user_id:
            return "someone"
        async with self._lock:
            if user_id in self._cache:
                return self._cache[user_id]
        display = user_id
        try:
            resp = await client.users_info(user=user_id)
            profile = resp["user"].get("profile", {})
            display = (
                profile.get("display_name")
                or profile.get("real_name")
                or resp["user"].get("name")
                or user_id
            )
        except Exception:
            logger.debug("Could not resolve display name for %s", user_id, exc_info=True)
        async with self._lock:
            self._cache[user_id] = display
        return display


async def _resolve_mentions(client: AsyncWebClient, text: str, resolver: NameResolver) -> str:
    """Replace ``<@Uxxx>`` mention tokens with readable @names."""
    ids = set(_MENTION_RE.findall(text))
    for uid in ids:
        name = await resolver.name(client, uid)
        text = text.replace(f"<@{uid}>", f"@{name}")
    return text


async def fetch_thread_history(
    *,
    client: AsyncWebClient,
    channel_id: str,
    thread_ts: str,
    bot_user_id: str,
    exclude_ts: str,
    resolver: NameResolver,
    limit: int = 100,
) -> list[ModelMessage]:
    """Rebuild pydantic-ai message history from a Slack thread.

    Every human message (from any participant) becomes a user turn prefixed with
    the speaker's name; every message from this bot becomes an assistant turn.
    The current triggering message (``exclude_ts``) is left out — it is passed
    separately as the live user content. Consecutive same-role messages are
    merged so the history stays well-formed for the model provider.

    Returns an empty list on any failure; the caller falls back to its cache.
    """
    try:
        resp = await client.conversations_replies(channel=channel_id, ts=thread_ts, limit=limit)
    except Exception:
        logger.info("Could not fetch thread replies; falling back to cached history")
        return []

    # (is_bot, text) in chronological order.
    turns: list[tuple[bool, str]] = []
    for msg in resp.get("messages", []):
        if msg.get("ts") == exclude_ts:
            continue
        if msg.get("subtype") in {"channel_join", "channel_leave", "thread_broadcast"}:
            continue
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        author = msg.get("user") or msg.get("bot_id") or ""
        is_bot = bool(msg.get("bot_id")) or author == bot_user_id
        text = await _resolve_mentions(client, text, resolver)
        if not is_bot:
            speaker = await resolver.name(client, author)
            text = f"{speaker}: {text}"
        turns.append((is_bot, text))

    # Merge consecutive same-role turns into one message each.
    messages: list[ModelMessage] = []
    for is_bot, text in turns:
        if messages and isinstance(messages[-1], ModelResponse) == is_bot:
            last = messages[-1]
            part = last.parts[-1]
            if isinstance(part, (TextPart, UserPromptPart)):
                part.content = f"{part.content}\n{text}"
                continue
        if is_bot:
            messages.append(ModelResponse(parts=[TextPart(content=text)]))
        else:
            messages.append(ModelRequest(parts=[UserPromptPart(content=text)]))
    return messages
