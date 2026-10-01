from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic_ai import FunctionToolCallEvent, FunctionToolResultEvent
from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from clanker.slack.stream import run_agent_streaming


class FakeAgent:
    def __init__(self, events: list[object]) -> None:
        self.events = events

    @asynccontextmanager
    async def run_stream_events(self, *args, **kwargs):
        async def event_stream():
            for event in self.events:
                yield event

        yield event_stream()


async def test_tool_result_completes_and_uploads_review_pdf(tmp_path):
    pdf = tmp_path / "review.pdf"
    pdf.write_bytes(b"%PDF-fake")
    tool_call_id = "call_review"
    result_json = json.dumps({"ok": True, "pdf_path": str(pdf)})
    agent = FakeAgent(
        [
            FunctionToolCallEvent(
                part=ToolCallPart(
                    tool_name="run_review", args={"cert_id": "c1"}, tool_call_id=tool_call_id
                )
            ),
            FunctionToolResultEvent(
                part=ToolReturnPart(
                    tool_name="run_review",
                    content=result_json,
                    tool_call_id=tool_call_id,
                )
            ),
        ]
    )
    streamer = SimpleNamespace(append=AsyncMock(), stop=AsyncMock())
    client = SimpleNamespace(
        chat_stream=AsyncMock(return_value=streamer),
        files_upload_v2=AsyncMock(),
    )
    store = AsyncMock()

    await run_agent_streaming(
        agent=agent,
        user_content="review c1",
        message_history=[],
        client=client,
        channel_id="C123",
        thread_ts="111.222",
        team_id="T123",
        user_id="U123",
        store=store,
        thread_key=("T123", "C123", "111.222"),
    )

    statuses = [
        call.kwargs["chunks"][0].status
        for call in streamer.append.await_args_list
        if call.kwargs.get("chunks")
    ]
    assert statuses == ["in_progress", "complete"]
    client.files_upload_v2.assert_awaited_once_with(
        channel="C123",
        thread_ts="111.222",
        file=str(pdf),
        filename="review_report.pdf",
        initial_comment="",
    )
    assert not any(
        "An error occurred" in (call.kwargs.get("markdown_text") or "")
        for call in streamer.append.await_args_list
    )
    streamer.stop.assert_awaited_once()


async def test_tool_result_uploads_review_pdf_and_video(tmp_path):
    pdf = tmp_path / "review.pdf"
    video = tmp_path / "review.mp4"
    pdf.write_bytes(b"%PDF-fake")
    video.write_bytes(b"mp4")
    event = FunctionToolResultEvent(
        part=ToolReturnPart(
            tool_name="run_review",
            content=json.dumps({"ok": True, "pdf_path": str(pdf), "video_path": str(video)}),
            tool_call_id="call_review",
        )
    )
    streamer = SimpleNamespace(append=AsyncMock(), stop=AsyncMock())
    client = SimpleNamespace(
        chat_stream=AsyncMock(return_value=streamer),
        files_upload_v2=AsyncMock(),
    )

    await run_agent_streaming(
        agent=FakeAgent([event]),
        user_content="review c1",
        message_history=[],
        client=client,
        channel_id="C123",
        thread_ts="111.222",
        team_id="T123",
        user_id="U123",
        store=AsyncMock(),
        thread_key=("T123", "C123", "111.222"),
    )

    assert client.files_upload_v2.await_count == 2
    assert [call.kwargs["filename"] for call in client.files_upload_v2.call_args_list] == [
        "review_report.pdf",
        "review_walkthrough.mp4",
    ]


async def test_unsuccessful_tool_result_is_error_and_does_not_upload(tmp_path):
    pdf = tmp_path / "review.pdf"
    pdf.write_bytes(b"%PDF-fake")
    event = FunctionToolResultEvent(
        part=ToolReturnPart(
            tool_name="run_review",
            content=json.dumps({"ok": False, "pdf_path": str(pdf)}),
            tool_call_id="call_review",
            outcome="interrupted",
        )
    )
    streamer = SimpleNamespace(append=AsyncMock(), stop=AsyncMock())
    client = SimpleNamespace(
        chat_stream=AsyncMock(return_value=streamer),
        files_upload_v2=AsyncMock(),
    )

    await run_agent_streaming(
        agent=FakeAgent([event]),
        user_content="review c1",
        message_history=[],
        client=client,
        channel_id="C123",
        thread_ts="111.222",
        team_id="T123",
        user_id="U123",
        store=AsyncMock(),
        thread_key=("T123", "C123", "111.222"),
    )

    chunk = streamer.append.await_args.kwargs["chunks"][0]
    assert chunk.status == "error"
    client.files_upload_v2.assert_not_awaited()
