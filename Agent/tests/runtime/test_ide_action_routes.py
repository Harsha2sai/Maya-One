from __future__ import annotations

import json

import pytest
from aiohttp import ClientSession, web

from api.handlers import (
    handle_ide_action_approve,
    handle_ide_action_audit,
    handle_ide_action_pending,
    handle_ide_action_request,
    handle_ide_mcp_inventory,
    handle_ide_mcp_mutate,
)
from core.ide import ActionGuard, IDEStateBus, PendingActionStore


async def _post_json(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    async with ClientSession() as session:
        response = await session.post(
            f"{base_url}{path}",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
        )
        body = await response.json()
        return response.status, body


async def _get_json(base_url: str, path: str) -> tuple[int, dict]:
    async with ClientSession() as session:
        response = await session.get(f"{base_url}{path}")
        body = await response.json()
        return response.status, body


@pytest.mark.asyncio
async def test_action_request_executes_low_risk(monkeypatch, unused_tcp_port):
    guard = ActionGuard()
    store = PendingActionStore()
    bus = IDEStateBus()
    monkeypatch.setattr(
        "api.handlers._get_pending_action_components",
        lambda: (guard, store, bus),
    )

    async def _fake_execute(**kwargs):
        del kwargs
        return {"executed": True}

    monkeypatch.setattr("api.handlers._execute_ide_action", _fake_execute)

    app = web.Application()
    app.router.add_post("/ide/action/request", handle_ide_action_request)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/ide/action/request",
            {
                "user_id": "u1",
                "session_id": "sess-1",
                "idempotency_key": "idem-1",
                "action": {
                    "target": "agent",
                    "operation": "retry",
                    "arguments": {"task_id": "task-1"},
                },
            },
        )
        assert status == 200
        assert body["status"] == "executed"
        assert body["requires_approval"] is False
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_action_request_requires_approval(monkeypatch, unused_tcp_port):
    guard = ActionGuard()
    store = PendingActionStore()
    bus = IDEStateBus()
    monkeypatch.setattr(
        "api.handlers._get_pending_action_components",
        lambda: (guard, store, bus),
    )

    app = web.Application()
    app.router.add_post("/ide/action/request", handle_ide_action_request)
    app.router.add_get("/ide/action/pending", handle_ide_action_pending)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/ide/action/request",
            {
                "user_id": "u1",
                "session_id": "sess-1",
                "idempotency_key": "idem-2",
                "action": {
                    "target": "mcp",
                    "operation": "set_url",
                    "arguments": {"url": "http://localhost:5678"},
                },
            },
        )
        assert status == 200
        assert body["status"] == "pending"
        assert body["requires_approval"] is True

        status, pending = await _get_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/ide/action/pending?user_id=u1",
        )
        assert status == 200
        assert len(pending["actions"]) == 1
        assert pending["actions"][0]["action_type"] == "mcp:set_url"
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_action_approve_executes_and_audits(monkeypatch, unused_tcp_port):
    guard = ActionGuard()
    store = PendingActionStore()
    bus = IDEStateBus()
    monkeypatch.setattr(
        "api.handlers._get_pending_action_components",
        lambda: (guard, store, bus),
    )

    async def _fake_execute(**kwargs):
        del kwargs
        return {"ok": True}

    monkeypatch.setattr("api.handlers._execute_ide_action", _fake_execute)

    action = await store.request(
        user_id="u1",
        session_id="sess-1",
        action_type="mcp:set_url",
        target_id="n8n",
        payload={"action": {"target": "mcp", "operation": "set_url", "arguments": {"url": "http://x"}}},
        risk="high",
        policy_reason="approval required",
        idempotency_key="idem-3",
    )

    app = web.Application()
    app.router.add_post("/ide/action/approve", handle_ide_action_approve)
    app.router.add_get("/ide/action/audit", handle_ide_action_audit)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/ide/action/approve",
            {"action_id": action.action_id, "decided_by": "admin", "reason": "safe"},
        )
        assert status == 200
        assert body["status"] == "executed"

        status, audit = await _get_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/ide/action/audit?user_id=u1",
        )
        assert status == 200
        event_types = {event["event_type"] for event in audit["events"]}
        assert "requested" in event_types
        assert "approved" in event_types
        assert "executed" in event_types
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_mcp_inventory_and_mutate(monkeypatch, unused_tcp_port):
    guard = ActionGuard()
    store = PendingActionStore()
    bus = IDEStateBus()
    monkeypatch.setattr(
        "api.handlers._get_pending_action_components",
        lambda: (guard, store, bus),
    )

    app = web.Application()
    app.router.add_get("/ide/mcp/inventory", handle_ide_mcp_inventory)
    app.router.add_post("/ide/mcp/mutate", handle_ide_mcp_mutate)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _get_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/ide/mcp/inventory",
        )
        assert status == 200
        assert "mcp_servers" in body
        assert "plugins" in body
        assert "connectors" in body

        status, mutate = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/ide/mcp/mutate",
            {
                "user_id": "u1",
                "session_id": "sess-1",
                "idempotency_key": "idem-4",
                "action": {
                    "target": "mcp",
                    "operation": "set_url",
                    "arguments": {"url": "http://localhost:8765"},
                },
            },
        )
        assert status == 200
        assert mutate["status"] == "pending"
    finally:
        await runner.cleanup()
