import asyncio

import pytest

from core.messaging.message_bus import MessageBus, MessageBusBackpressureError


@pytest.mark.asyncio
async def test_message_bus_envelope_contains_required_fields():
    bus = MessageBus(max_queue_depth=10)
    captured = []

    async def _handler(envelope):
        captured.append(envelope)

    await bus.subscribe("agent.progress", _handler)
    envelope = await bus.publish(
        "agent.progress",
        {"status": "started"},
        trace_id="trace-1",
        handoff_id="handoff-1",
        task_id="task-1",
        checkpoint_id="chk-1",
    )

    assert envelope.trace_id == "trace-1"
    assert envelope.handoff_id == "handoff-1"
    assert envelope.task_id == "task-1"
    assert envelope.message_id
    assert envelope.timestamp > 0
    assert captured and captured[0].message_id == envelope.message_id


@pytest.mark.asyncio
async def test_message_bus_enforces_global_depth_cap():
    gate = asyncio.Event()
    bus = MessageBus(max_queue_depth=1)

    async def _handler(_envelope):
        await gate.wait()

    await bus.subscribe("agent.command", _handler)
    first = asyncio.create_task(bus.publish("agent.command", {"op": "run"}))
    await asyncio.sleep(0.01)

    with pytest.raises(MessageBusBackpressureError):
        await bus.publish("agent.command", {"op": "run2"})

    gate.set()
    await first

