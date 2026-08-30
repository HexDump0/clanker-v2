"""Slack Bolt (Socket Mode) chat bot: @mention the bot in the watch channel."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

from slack_bolt.app.async_app import AsyncApp
from slack_bolt.context.async_context import AsyncBoltContext

from clanker.config import Settings
from clanker.slack.history import ConversationStore, NameResolver, fetch_thread_history
from clanker.slack.stream import run_agent_streaming

if TYPE_CHECKING:
    from pydantic_ai import Agent

logger = logging.getLogger(__name__)

_MENTION_RE = re.compile(r"<@[A-Z0-9]+>\s*")

# Batching / auto-follow config
BATCH_WINDOW = 1.2  # seconds to wait after last thread message before responding
WATCH_TTL_SECS = 3 * 3600  # forget watched threads after 3h


def _is_parent_mention(event: dict) -> bool:
    """True if this app_mention created a new thread (not a reply in an existing one)."""
    thread_ts = event.get("thread_ts")
    ts = event.get("ts")
    if not thread_ts:
        return True
    return thread_ts == ts


def create_slack_app(settings: Settings, chat_agent: Agent) -> AsyncApp:
    settings.require_slack()
    app = AsyncApp(token=settings.slack_bot_token)
    store = ConversationStore()
    names = NameResolver()

    # Auto-follow state: threads that were created by a parent @mention.
    # Key is (channel, thread_ts) — team is ignored to avoid mismatches between
    # app_mention and message events (context.team_id vs event.team).
    watched: dict[tuple[str, str], float] = {}
    pending: dict[tuple[str, str], list[dict[str, Any]]] = {}
    debounce_tasks: dict[tuple[str, str], asyncio.Task] = {}
    processing_locks: dict[tuple[str, str], asyncio.Lock] = {}

    def _purge_expired(now: float) -> None:
        expired = [k for k, ts in watched.items() if now - ts > WATCH_TTL_SECS]
        for k in expired:
            watched.pop(k, None)
            pending.pop(k, None)
            task = debounce_tasks.pop(k, None)
            if task and not task.done():
                task.cancel()
            processing_locks.pop(k, None)

    async def _process_batch(
        thread_key: tuple[str, str],
        batch: list[dict[str, Any]],
        client,
        bot_user_id: str,
        team_id: str,
    ) -> None:
        channel_id, thread_ts = thread_key
        if not batch:
            return

        # Build combined text - ignore files/images per user request
        texts: list[str] = []
        for ev in batch:
            raw_text = (ev.get("text") or "").strip()
            cleaned = _MENTION_RE.sub("", raw_text).strip()
            if not cleaned:
                continue
            user_id = ev.get("user") or ""
            display = await names.name(client, user_id) if user_id else "someone"
            if len(batch) > 1:
                texts.append(f"{display}: {cleaned}")
            else:
                texts.append(cleaned)

        combined_text = "\n".join(texts).strip()
        if not combined_text:
            logger.debug("Skipping batch in %s: no text", thread_key)
            return

        if len(batch) > 1:
            combined_text = f"New messages in thread (batched {len(batch)}):\n{combined_text}"

        # Build history excluding this batch's ts's
        exclude = {ev.get("ts") for ev in batch if ev.get("ts")}
        history = []
        # Store key still needs team for ConversationStore compatibility
        store_key = (team_id, channel_id, thread_ts)
        try:
            resp = await client.conversations_replies(
                channel=channel_id, ts=thread_ts, limit=100
            )
            from pydantic_ai.messages import (
                ModelMessage,
                ModelRequest,
                ModelResponse,
                TextPart,
                UserPromptPart,
            )

            turns: list[tuple[bool, str]] = []
            for msg in resp.get("messages", []):
                if msg.get("ts") in exclude:
                    continue
                if msg.get("subtype") in {"channel_join", "channel_leave", "thread_broadcast"}:
                    continue
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                author = msg.get("user") or msg.get("bot_id") or ""
                is_bot = bool(msg.get("bot_id")) or author == bot_user_id
                if not is_bot:
                    for uid in set(re.findall(r"<@([A-Z0-9]+)>", text)):
                        try:
                            name = await names.name(client, uid)
                            text = text.replace(f"<@{uid}>", f"@{name}")
                        except Exception:
                            pass
                    speaker = await names.name(client, author) if author else "someone"
                    text = f"{speaker}: {text}"
                turns.append((is_bot, text))

            history_messages: list[ModelMessage] = []
            for is_bot, text in turns:
                if history_messages and isinstance(history_messages[-1], ModelResponse) == is_bot:
                    last = history_messages[-1]
                    part = last.parts[-1]
                    if isinstance(part, (TextPart, UserPromptPart)):
                        part.content = f"{part.content}\n{text}"
                        continue
                if is_bot:
                    history_messages.append(ModelResponse(parts=[TextPart(content=text)]))
                else:
                    history_messages.append(ModelRequest(parts=[UserPromptPart(content=text)]))
            history = history_messages
        except Exception:
            logger.info("Could not fetch thread replies for batch; falling back to cached history")
            history = await store.get(store_key)

        if not history:
            history = await store.get(store_key)

        last_user = batch[-1].get("user", "") or ""
        try:
            await run_agent_streaming(
                agent=chat_agent,
                user_content=combined_text,
                message_history=history,
                client=client,
                channel_id=channel_id,
                thread_ts=thread_ts,
                team_id=team_id,
                user_id=last_user,
                store=store,
                thread_key=store_key,
            )
        except Exception:
            logger.exception("Failed to run agent for batched messages %s", thread_key)
            try:
                await client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=":warning: Something went wrong.",
                )
            except Exception:
                pass

    async def _debounce(
        thread_key: tuple[str, str],
        client,
        bot_user_id: str,
        team_id: str,
    ) -> None:
        try:
            await asyncio.sleep(BATCH_WINDOW)
        except asyncio.CancelledError:
            return
        batch = pending.pop(thread_key, [])
        if not batch:
            debounce_tasks.pop(thread_key, None)
            return
        debounce_tasks.pop(thread_key, None)
        lock = processing_locks.setdefault(thread_key, asyncio.Lock())
        async with lock:
            try:
                await _process_batch(thread_key, batch, client, bot_user_id, team_id)
            except Exception:
                logger.exception("Batch processing error for %s", thread_key)

    @app.event("app_mention")
    async def handle_app_mention(event: dict, client, context: AsyncBoltContext):
        channel_id = event["channel"]
        user_message = _MENTION_RE.sub("", event.get("text", "")).strip()
        if not user_message:
            return
        thread_ts = event.get("thread_ts") or event["ts"]
        team_id = context.team_id or event.get("team") or ""
        thread_key = (channel_id, thread_ts)
        store_key = (team_id, channel_id, thread_ts)

        is_parent = _is_parent_mention(event)
        if is_parent:
            now = asyncio.get_event_loop().time()
            _purge_expired(now)
            watched[thread_key] = now
            pending.setdefault(thread_key, [])
            logger.info("Watching thread %s (parent)", thread_key)
        else:
            logger.info("Mention inside existing thread %s - single", thread_key)

        try:
            history = await fetch_thread_history(
                client=client,
                channel_id=channel_id,
                thread_ts=thread_ts,
                bot_user_id=context.bot_user_id or "",
                exclude_ts=event["ts"],
                resolver=names,
            )
            if not history:
                history = await store.get(store_key)

            await run_agent_streaming(
                agent=chat_agent,
                user_content=user_message,
                message_history=history,
                client=client,
                channel_id=channel_id,
                thread_ts=thread_ts,
                team_id=team_id,
                user_id=event.get("user", ""),
                store=store,
                thread_key=store_key,
            )
        except Exception:
            logger.exception("Failed to run agent for @mention")
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=":warning: Something went wrong. Please try again.",
            )

    @app.event("message")
    async def handle_thread_message(event: dict, client, context: AsyncBoltContext):
        # Auto-follow in threads that were activated by a parent @mention.
        # Ignore bot messages and non-thread messages. Ignore files/images.
        logger.debug(
            "message event: subtype=%s thread_ts=%s ts=%s channel=%s text=%.50r watched=%s",
            event.get("subtype"),
            event.get("thread_ts"),
            event.get("ts"),
            event.get("channel"),
            (event.get("text") or "")[:50],
            list(watched.keys())[:3],
        )
        subtype = event.get("subtype")
        if subtype not in (None, "file_share"):
            return
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return
        ts = event.get("ts")
        if ts == thread_ts:
            return
        channel_id = event.get("channel")
        if not channel_id:
            return
        thread_key = (channel_id, thread_ts)
        if thread_key not in watched:
            logger.debug("thread %s not watched, ignoring", thread_key)
            return
        if event.get("bot_id"):
            return
        bot_uid = context.bot_user_id or ""
        if bot_uid and event.get("user") == bot_uid:
            return
        if event.get("user") is None:
            return
        text = _MENTION_RE.sub("", (event.get("text") or "")).strip()
        if not text:
            logger.debug("Ignoring message without text in thread %s", thread_key)
            return

        logger.info("Enqueue thread message %s in %s: %.80r", event.get("ts"), thread_key, text)
        now = asyncio.get_event_loop().time()
        watched[thread_key] = now
        _purge_expired(now)

        team_id = context.team_id or event.get("team") or ""
        pending.setdefault(thread_key, []).append(event)

        old = debounce_tasks.get(thread_key)
        if old and not old.done():
            old.cancel()
        debounce_tasks[thread_key] = asyncio.create_task(
            _debounce(thread_key, client, bot_uid, team_id)
        )

    return app
