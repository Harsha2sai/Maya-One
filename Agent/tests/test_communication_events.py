from __future__ import annotations

import asyncio
import json

import pytest

from core.ide import IDEStateBus
from core.communication import (
    publish_chat_event,
    publish_confirmation_required,
    publish_error_event,
    publish_media_result,
    publish_research_result,
    publish_system_result,
    publish_tool_execution,
    publish_user_message,
)
from core.events.agent_events import SCHEMA_VERSION


class _FakeLocalParticipant:
    def __init__(self) -> None:
        self.published: list[tuple[bytes, str]] = []
        self.sent_text: list[tuple[str, str]] = []

    async def publish_data(self, payload: bytes, topic: str) -> None:
        self.published.append((payload, topic))

    async def send_text(self, text: str, topic: str) -> None:
        self.sent_text.append((text, topic))


class _FakeRoom:
    def __init__(self) -> None:
        self.local_participant = _FakeLocalParticipant()


@pytest.mark.asyncio
async def test_publish_user_message_includes_schema_version_and_trace() -> None:
    room = _FakeRoom()
    ok = await publish_user_message(room, "turn-1", "hello")
    assert ok is True
    payload, topic = room.local_participant.published[-1]
    data = json.loads(payload.decode("utf-8"))
    assert topic == "chat_events"
    assert data["type"] == "user_message"
    assert data["schema_version"] == SCHEMA_VERSION
    assert isinstance(data["trace_id"], str) and data["trace_id"]


@pytest.mark.asyncio
async def test_publish_tool_execution_emits_canonical_and_alias_fields() -> None:
    room = _FakeRoom()
    ok = await publish_tool_execution(
        room,
        "turn-2",
        "web_search",
        "started",
        task_id="task-123",
        conversation_id="conversation-123",
    )
    assert ok is True
    payload, _topic = room.local_participant.published[-1]
    data = json.loads(payload.decode("utf-8"))
    assert data["tool_name"] == "web_search"
    assert data["tool"] == "web_search"
    assert data["task_id"] == "task-123"
    assert data["conversation_id"] == "conversation-123"
    assert data["schema_version"] == SCHEMA_VERSION


@pytest.mark.asyncio
async def test_invalid_payload_dropped_by_publish_chat_event() -> None:
    room = _FakeRoom()
    ok = await publish_chat_event(
        room,
        {
            "type": "agent_thinking",
            "turn_id": "turn-3",
            "state": "thinking",
            # Missing schema_version/timestamp are auto-filled, but this unknown extra should fail.
            "unexpected": "x",
        },
    )
    assert ok is False
    assert room.local_participant.published == []


@pytest.mark.asyncio
async def test_publish_error_event_uses_safe_message_when_empty() -> None:
    room = _FakeRoom()
    ok = await publish_error_event(room, turn_id="turn-4", message="", code="x")
    assert ok is True
    payload, _topic = room.local_participant.published[-1]
    data = json.loads(payload.decode("utf-8"))
    assert data["type"] == "error"
    assert data["message"] == "I ran into an issue while processing that. Please try again."
    assert data["code"] == "x"


@pytest.mark.asyncio
async def test_publish_research_result_event() -> None:
    room = _FakeRoom()
    ok = await publish_research_result(
        room,
        turn_id="turn-5",
        query="latest ai news",
        summary="Top updates",
        sources=[
            {
                "title": "S1",
                "url": "https://example.com",
                "domain": "example.com",
                "snippet": "snippet",
                "provider": "tavily",
            }
        ],
        trace_id="trace-1",
    )
    assert ok is True
    payload, _topic = room.local_participant.published[-1]
    data = json.loads(payload.decode("utf-8"))
    assert data["type"] == "research_result"
    assert data["query"] == "latest ai news"
    assert data["sources"][0]["domain"] == "example.com"


@pytest.mark.asyncio
async def test_publish_media_result_event() -> None:
    room = _FakeRoom()
    ok = await publish_media_result(
        room,
        turn_id="turn-media",
        action="play",
        provider="spotify",
        track_name="Song A",
        artist="Artist A",
        track_url="https://open.spotify.com/track/abc",
        album_art_url="https://img.test/1.png",
        trace_id="trace-2",
    )
    assert ok is True
    payload, _topic = room.local_participant.published[-1]
    data = json.loads(payload.decode("utf-8"))
    assert data["type"] == "media_result"
    assert data["provider"] == "spotify"
    assert data["track_name"] == "Song A"


@pytest.mark.asyncio
async def test_publish_system_result_event() -> None:
    room = _FakeRoom()
    ok = await publish_system_result(
        room,
        turn_id="turn-system",
        action_type="SCREENSHOT",
        success=True,
        message="Saved screenshot.",
        detail="/tmp/maya_screen.png",
        rollback_available=False,
        trace_id="trace-system",
        task_id="task-system-1",
        conversation_id="conversation-9",
    )
    assert ok is True
    payload, _topic = room.local_participant.published[-1]
    data = json.loads(payload.decode("utf-8"))
    assert data["type"] == "system_result"
    assert data["turn_id"] == "turn-system"
    assert data["action_type"] == "SCREENSHOT"
    assert data["trace_id"] == "trace-system"
    assert data["task_id"] == "task-system-1"
    assert data["conversation_id"] == "conversation-9"


@pytest.mark.asyncio
async def test_publish_confirmation_required_event() -> None:
    room = _FakeRoom()
    ok = await publish_confirmation_required(
        room,
        action_type="FILE_DELETE",
        description="Delete test.txt",
        destructive=True,
        timeout_seconds=30,
        trace_id="trace-confirm",
    )
    assert ok is True
    payload, _topic = room.local_participant.published[-1]
    data = json.loads(payload.decode("utf-8"))
    assert data["type"] == "confirmation_required"
    assert data["destructive"] is True
    assert data["timeout_seconds"] == 30


@pytest.mark.asyncio
async def test_publish_tool_execution_bridges_to_ide_state_bus(monkeypatch: pytest.MonkeyPatch) -> None:
    room = _FakeRoom()
    bus = IDEStateBus()
    queue = bus.subscribe()

    monkeypatch.setattr(
        "core.runtime.global_agent.GlobalAgentContainer.get_ide_state_bus",
        classmethod(lambda _cls: bus),
    )

    ok = await publish_tool_execution(
        room,
        "turn-bridge-1",
        "web_search",
        "started",
        task_id="task-bridge-1",
    )
    assert ok is True

    first = await asyncio.wait_for(queue.get(), timeout=1.0)
    second = await asyncio.wait_for(queue.get(), timeout=1.0)
    event_types = {first["event_type"], second["event_type"]}
    assert "tool_started" in event_types
    assert "task_step" in event_types


@pytest.mark.asyncio
async def test_publish_error_event_bridges_task_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    room = _FakeRoom()
    bus = IDEStateBus()
    queue = bus.subscribe()

    monkeypatch.setattr(
        "core.runtime.global_agent.GlobalAgentContainer.get_ide_state_bus",
        classmethod(lambda _cls: bus),
    )

    ok = await publish_error_event(room, turn_id="turn-fail", message="boom", code="E_FAIL")
    assert ok is True

    bridged = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert bridged["event_type"] == "task_failed"
    assert bridged["status"] == "error"
