import pytest

from core.messaging.message_bus import MessageBus
from core.messaging.progress_stream import ProgressStream


@pytest.mark.asyncio
async def test_progress_stream_throttles_non_terminal_updates():
    bus = MessageBus(max_queue_depth=20)
    received = []

    async def _handler(envelope):
        received.append(envelope.payload)

    bus.subscribe("agent.progress", _handler)

    now = [0.0]
    stream = ProgressStream(message_bus=bus, max_events_per_sec=2, clock=lambda: now[0])

    first = await stream.emit_progress(
        task_id="task-1",
        session_id="sess-1",
        agent="subagent_coder",
        phase="compile",
        status="running",
        percent=10,
        summary="started",
    )
    second = await stream.emit_progress(
        task_id="task-1",
        session_id="sess-1",
        agent="subagent_coder",
        phase="compile",
        status="running",
        percent=11,
        summary="still running",
    )

    assert first is not None
    assert second is None
    assert len(received) == 1

    now[0] = 0.6
    third = await stream.emit_progress(
        task_id="task-1",
        session_id="sess-1",
        agent="subagent_coder",
        phase="compile",
        status="running",
        percent=50,
        summary="halfway",
    )
    assert third is not None
    assert len(received) == 2


@pytest.mark.asyncio
async def test_progress_stream_terminal_status_bypasses_throttle():
    bus = MessageBus(max_queue_depth=20)
    received = []

    async def _handler(envelope):
        received.append(envelope.payload)

    bus.subscribe("agent.progress", _handler)

    now = [0.0]
    stream = ProgressStream(message_bus=bus, max_events_per_sec=1, clock=lambda: now[0])

    await stream.emit_progress(
        task_id="task-2",
        session_id="sess-2",
        agent="subagent_reviewer",
        phase="review",
        status="running",
        percent=80,
        summary="almost done",
    )
    result = await stream.emit_progress(
        task_id="task-2",
        session_id="sess-2",
        agent="subagent_reviewer",
        phase="review",
        status="failed",
        percent=100,
        summary="failed",
    )

    assert result is not None
    assert len(received) == 2
    assert received[-1]["status"] == "failed"
