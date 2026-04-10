import asyncio

import pytest

from core.messaging.message_bus import MessageBus, MessageBusBackpressureError


@pytest.mark.asyncio
async def test_publish_subscribe_and_unsubscribe_round_trip():
    bus = MessageBus(max_queue_depth=10)
    received = []

    async def _handler(envelope):
        received.append(envelope)

    bus.subscribe("agent.progress", _handler)
    result = await bus.publish(
        "agent.progress",
        {"status": "running"},
        trace_id="trace-1",
        handoff_id="handoff-1",
        task_id="task-1",
        metadata={"source": "test"},
    )

    assert result["topic"] == "agent.progress"
    assert result["trace_id"] == "trace-1"
    assert result["handoff_id"] == "handoff-1"
    assert result["task_id"] == "task-1"
    assert received and received[0].payload["status"] == "running"

    bus.unsubscribe("agent.progress", _handler)
    await bus.publish("agent.progress", {"status": "completed"})
    assert len(received) == 1


@pytest.mark.asyncio
async def test_backpressure_raises_when_queue_is_full():
    bus = MessageBus(max_queue_depth=1)

    await bus._drain_lock.acquire()
    first_publish = asyncio.create_task(bus.publish("topic", {"idx": 1}))
    await asyncio.sleep(0)

    with pytest.raises(MessageBusBackpressureError):
        await bus.publish("topic", {"idx": 2})

    bus._drain_lock.release()
    await first_publish
