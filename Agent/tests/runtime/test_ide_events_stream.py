from __future__ import annotations

import json

import pytest
from aiohttp import ClientSession, WSMsgType, web

from api.handlers import handle_ide_events_stream
from core.ide import IDEStateBus


async def _ws_receive_json(ws, *, timeout: float = 2.0) -> dict:
    message = await ws.receive(timeout=timeout)
    assert message.type == WSMsgType.TEXT
    return json.loads(message.data)


@pytest.mark.asyncio
async def test_ide_events_stream_replay_and_live_filtering(monkeypatch, unused_tcp_port):
    bus = IDEStateBus(replay_size=100)
    monkeypatch.setattr(
        "api.handlers._get_ide_runtime_components",
        lambda: (object(), object(), object(), bus),
    )

    await bus.emit("task_started", {"session_id": "s1", "task_id": "task-1"})
    await bus.emit("task_started", {"session_id": "s2", "task_id": "task-2"})

    app = web.Application()
    app.router.add_get("/ide/events/stream", handle_ide_events_stream)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        async with ClientSession() as session:
            ws = await session.ws_connect(
                f"http://127.0.0.1:{unused_tcp_port}/ide/events/stream?session_id=s1&after_seq=0&limit=10"
            )

            first = await _ws_receive_json(ws)
            assert first["event_type"] == "task_started"
            assert first["session_id"] == "s1"
            assert first["task_id"] == "task-1"

            # s2 should be filtered out from live stream for this socket.
            await bus.emit("task_step", {"session_id": "s2", "task_id": "task-2"})
            await bus.emit("task_step", {"session_id": "s1", "task_id": "task-1"})
            live = await _ws_receive_json(ws)
            assert live["event_type"] == "task_step"
            assert live["session_id"] == "s1"

            await ws.close()
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_ide_events_stream_reconnect_replay_from_after_seq(monkeypatch, unused_tcp_port):
    bus = IDEStateBus(replay_size=100)
    monkeypatch.setattr(
        "api.handlers._get_ide_runtime_components",
        lambda: (object(), object(), object(), bus),
    )

    first = await bus.emit("task_started", {"session_id": "s1", "task_id": "task-1"})
    second = await bus.emit("task_step", {"session_id": "s1", "task_id": "task-1"})
    third = await bus.emit("task_finished", {"session_id": "s1", "task_id": "task-1"})

    app = web.Application()
    app.router.add_get("/ide/events/stream", handle_ide_events_stream)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        async with ClientSession() as session:
            ws = await session.ws_connect(
                f"http://127.0.0.1:{unused_tcp_port}/ide/events/stream?session_id=s1&after_seq={first['seq']}&limit=10"
            )
            replay_one = await _ws_receive_json(ws)
            replay_two = await _ws_receive_json(ws)

            assert replay_one["seq"] == second["seq"]
            assert replay_two["seq"] == third["seq"]
            assert replay_two["event_type"] == "task_finished"
            await ws.close()
    finally:
        await runner.cleanup()
