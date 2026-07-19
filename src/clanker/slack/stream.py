"""Bridges pydantic-ai streaming events to Slack chat_stream."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING

from pydantic_ai import (
    AgentRunResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPartDelta,
)
from pydantic_ai.messages import ModelMessage, TextPart
from slack_sdk.errors import SlackApiError
from slack_sdk.models.messages.chunk import TaskUpdateChunk

if TYPE_CHECKING:
    from pydantic_ai import Agent
    from slack_sdk.web.async_client import AsyncWebClient

    from clanker.slack.history import ConversationStore, ThreadKey

logger = logging.getLogger(__name__)

FLUSH_INTERVAL = 0.4  # seconds between Slack flushes

# Tools whose JSON result carries a file to drop into the thread.
_FILE_RESULT_TOOLS = {"run_review": ("pdf_path", "review_report.pdf")}


async def run_agent_streaming(
    *,
    agent: Agent,
    user_content: str | list,
    message_history: list[ModelMessage],
    client: AsyncWebClient,
    channel_id: str,
    thread_ts: str,
    team_id: str,
    user_id: str,
    store: ConversationStore,
    thread_key: ThreadKey,
) -> None:
    """Run the agent with event streaming, piping output to Slack chat_stream."""
    streamer = await client.chat_stream(
        channel=channel_id,
        thread_ts=thread_ts,
        recipient_team_id=team_id,
        recipient_user_id=user_id,
        task_display_mode="timeline",
        buffer_size=512,
    )

    text_buffer = ""
    last_flush = asyncio.get_event_loop().time()
    tool_id_counter = 0
    stream_alive = True
    flush_task: asyncio.Task | None = None

    def _is_dead_stream(exc: SlackApiError) -> bool:
        try:
            dead = exc.response.get("error") == "message_not_in_streaming_state"
            return bool(exc.response) and dead
        except Exception:
            return False

    async def safe_append(*, markdown_text: str | None = None, chunks: list | None = None) -> bool:
        nonlocal stream_alive
        if not stream_alive:
            return False
        try:
            await streamer.append(markdown_text=markdown_text, chunks=chunks or [])
            return True
        except SlackApiError as exc:
            if _is_dead_stream(exc):
                stream_alive = False
                logger.info("Slack stream no longer active; suppressing further appends")
                return False
            raise

    async def safe_stop() -> None:
        nonlocal stream_alive
        if not stream_alive:
            return
        try:
            await streamer.stop()
        except SlackApiError as exc:
            if _is_dead_stream(exc):
                stream_alive = False
                return
            raise

    async def flush_text() -> None:
        nonlocal text_buffer, last_flush, flush_task
        if not text_buffer:
            return
        if flush_task is not None and not flush_task.done():
            await flush_task
        chunk = text_buffer
        text_buffer = ""
        last_flush = asyncio.get_event_loop().time()
        flush_task = asyncio.create_task(safe_append(markdown_text=chunk))

    async def maybe_flush() -> None:
        if text_buffer and asyncio.get_event_loop().time() - last_flush >= FLUSH_INTERVAL:
            await flush_text()

    async def upload_tool_file(tool_name: str, content: object) -> None:
        path_key, filename = _FILE_RESULT_TOOLS[tool_name]
        try:
            parsed = json.loads(content) if isinstance(content, str) else {}
            file_path = parsed.get(path_key) or ""
            if file_path and os.path.isfile(file_path):
                await client.files_upload_v2(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    file=file_path,
                    filename=filename,
                    initial_comment="",
                )
        except Exception:
            logger.exception("Failed to upload %s result file to Slack", tool_name)

    try:
        result_event = None

        # pydantic-ai 2.x: run_stream_events is an async context manager.
        async with agent.run_stream_events(
            user_content, message_history=message_history
        ) as event_stream:
            async for event in event_stream:
                if isinstance(event, AgentRunResultEvent):
                    result_event = event

                elif isinstance(event, PartStartEvent):
                    if isinstance(event.part, TextPart) and event.part.content:
                        text_buffer += event.part.content
                        await maybe_flush()

                elif isinstance(event, PartDeltaEvent):
                    if isinstance(event.delta, TextPartDelta):
                        text_buffer += event.delta.content_delta
                        await maybe_flush()

                elif isinstance(event, FunctionToolCallEvent):
                    await flush_text()
                    tool_id_counter += 1
                    call_id = event.part.tool_call_id or f"tool_{tool_id_counter}"
                    await safe_append(
                        chunks=[
                            TaskUpdateChunk(
                                id=call_id,
                                title=f"Calling {event.part.tool_name}...",
                                status="in_progress",
                            )
                        ]
                    )

                elif isinstance(event, FunctionToolResultEvent):
                    await flush_text()
                    result_part = event.result
                    tool_name = getattr(result_part, "tool_name", None) or "tool"
                    call_id = result_part.tool_call_id or f"tool_{tool_id_counter}"
                    outcome = getattr(result_part, "outcome", "success")
                    await safe_append(
                        chunks=[
                            TaskUpdateChunk(
                                id=call_id,
                                title=tool_name,
                                status="error" if outcome == "failed" else "complete",
                            )
                        ]
                    )
                    if tool_name in _FILE_RESULT_TOOLS:
                        await upload_tool_file(tool_name, getattr(result_part, "content", ""))

        await flush_text()
        if flush_task is not None and not flush_task.done():
            await flush_task

        if result_event is not None:
            usage = result_event.result.usage
            logger.info(
                "[slack chat %s] tokens: %d in / %d out",
                channel_id,
                usage.input_tokens,
                usage.output_tokens,
            )
            await store.save(thread_key, result_event.result.all_messages())

    except Exception:
        logger.exception("Agent streaming error")
        if flush_task is not None and not flush_task.done():
            await flush_task
        if text_buffer:
            await safe_append(markdown_text=text_buffer)
        await safe_append(markdown_text="\n\n:warning: An error occurred while processing.")
    finally:
        await safe_stop()
