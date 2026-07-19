"""Slack Bolt (Socket Mode) chat bot: @mention the bot in the watch channel."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from slack_bolt.app.async_app import AsyncApp
from slack_bolt.context.async_context import AsyncBoltContext

from clanker.config import Settings
from clanker.slack.files import build_user_content
from clanker.slack.history import ConversationStore, NameResolver, fetch_thread_history
from clanker.slack.stream import run_agent_streaming

if TYPE_CHECKING:
    from pydantic_ai import Agent

logger = logging.getLogger(__name__)

_MENTION_RE = re.compile(r"<@[A-Z0-9]+>\s*")


def create_slack_app(settings: Settings, chat_agent: Agent) -> AsyncApp:
    settings.require_slack()
    app = AsyncApp(token=settings.slack_bot_token)
    store = ConversationStore()
    names = NameResolver()

    @app.event("app_mention")
    async def handle_app_mention(event: dict, client, context: AsyncBoltContext):
        channel_id = event["channel"]
        if channel_id != settings.slack_channel:
            return

        user_message = _MENTION_RE.sub("", event.get("text", "")).strip()
        files = event.get("files")
        if not user_message and not files:
            return
        thread_ts = event.get("thread_ts") or event["ts"]
        thread_key = (context.team_id or "", channel_id, thread_ts)

        try:
            try:
                user_content = await build_user_content(
                    text=user_message, files=files, bot_token=settings.slack_bot_token
                )
            except Exception:
                logger.exception("Failed to process attachments; falling back to text")
                user_content = user_message

            # Prefer the live Slack thread so Clanker sees the whole conversation
            # (including messages from before it was mentioned). Fall back to the
            # in-memory cache if the thread can't be read.
            history = await fetch_thread_history(
                client=client,
                channel_id=channel_id,
                thread_ts=thread_ts,
                bot_user_id=context.bot_user_id or "",
                exclude_ts=event["ts"],
                resolver=names,
            )
            if not history:
                history = await store.get(thread_key)

            await run_agent_streaming(
                agent=chat_agent,
                user_content=user_content,
                message_history=history,
                client=client,
                channel_id=channel_id,
                thread_ts=thread_ts,
                team_id=context.team_id or "",
                user_id=event.get("user", ""),
                store=store,
                thread_key=thread_key,
            )
        except Exception:
            logger.exception("Failed to run agent for @mention")
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=":warning: Something went wrong. Please try again.",
            )

    return app
