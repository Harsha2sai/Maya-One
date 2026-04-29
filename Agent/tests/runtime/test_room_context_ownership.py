from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from aiohttp import ClientSession, web

from api import handlers


async def _post_json(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    async with ClientSession() as session:
        response = await session.post(
            f"{base_url}{path}",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
        )
        body = await response.json()
        return response.status, body


@pytest.fixture(autouse=True)
def _reset_room_context_fixture():
    handlers.reset_room_context_state(reason="test_setup")
    try:
        yield
    finally:
        handlers.reset_room_context_state(reason="test_teardown")


def test_reset_room_context_state_bumps_generation_and_clears_run_map() -> None:
    initial = handlers.reset_room_context_state(reason="initial")
    handlers._last_room_by_run_id["run-1"] = {
        "room_name": "room-a",
        "generation": int(initial["generation"]),
        "issued_at_ms": 123,
    }

    updated = handlers.reset_room_context_state(reason="restart")

    assert int(updated["generation"]) == int(initial["generation"]) + 1
    assert updated["context_state"] == "empty"
    assert updated["reason"] == "restart"
    assert handlers._last_room_by_run_id == {}


@pytest.mark.asyncio
async def test_handle_send_message_rejects_send_before_token(unused_tcp_port: int) -> None:
    app = web.Application()
    app.router.add_post("/send_message", handlers.handle_send_message)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/send_message",
            {"message": "hello", "user_id": "u1", "run_id": "run-1"},
        )
    finally:
        await runner.cleanup()

    assert status == 409
    assert body["error"] == "room_context_send_before_token"
    assert body["details"]["context_state"] == "empty"


@pytest.mark.asyncio
async def test_handle_send_message_rejects_stale_generation(unused_tcp_port: int) -> None:
    stale = handlers._publish_token_room_context(
        room_name="room-old",
        participant_name="participant-old",
        token_status=200,
        context_state="token_issued",
    )
    handlers.reset_room_context_state(reason="restart")
    handlers._set_room_context(stale)

    app = web.Application()
    app.router.add_post("/send_message", handlers.handle_send_message)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/send_message",
            {"message": "hello", "user_id": "u1", "run_id": "run-1"},
        )
    finally:
        await runner.cleanup()

    assert status == 409
    assert body["error"] == "room_context_stale_generation"
    assert body["details"]["generation"] == stale["generation"]
    assert body["details"]["current_generation"] == handlers._current_room_context_generation()


@pytest.mark.asyncio
async def test_handle_send_message_rejects_token_failed_context(unused_tcp_port: int) -> None:
    handlers._publish_token_room_context(
        room_name="room-a",
        participant_name="participant-a",
        token_status=500,
        context_state="token_failed",
        reason="dispatch failed",
    )

    app = web.Application()
    app.router.add_post("/send_message", handlers.handle_send_message)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/send_message",
            {"message": "hello", "user_id": "u1", "run_id": "run-1"},
        )
    finally:
        await runner.cleanup()

    assert status == 409
    assert body["error"] == "room_context_token_failed"
    assert body["details"]["reason"] == "dispatch failed"


@pytest.mark.asyncio
async def test_handle_token_failure_publishes_failed_room_context(monkeypatch, unused_tcp_port: int) -> None:
    async def _fail_dispatch(_room_name: str):
        raise RuntimeError("dispatch failed")

    monkeypatch.setattr(handlers, "_ensure_room_dispatch", _fail_dispatch)
    monkeypatch.setattr(handlers, "get_runtime_readiness_tracker", lambda: _FakeTracker())

    app = web.Application()
    app.router.add_post("/token", handlers.handle_token)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/token",
            {"roomName": "room-a", "participantName": "participant-a"},
        )
    finally:
        await runner.cleanup()

    context = handlers._room_context_snapshot()
    assert status == 500
    assert body["error"] == "dispatch failed"
    assert context["context_state"] == "token_failed"
    assert context["token_status"] == 500
    assert context["room_name"] == "room-a"


class _FakeAccessToken:
    def __init__(self, *_args, **_kwargs):
        self.metadata = None

    def with_identity(self, _value):
        return self

    def with_name(self, _value):
        return self

    def with_grants(self, _value):
        return self

    def with_metadata(self, value):
        self.metadata = value
        return self

    def to_jwt(self):
        return "fake-jwt"


class _FakeTracker:
    def __init__(self, *, snapshots: list[dict] | None = None):
        self.events: list[tuple[str, dict]] = []
        default_snapshot = {
            "ready": True,
            "state": "READY_SESSION_CAPABLE",
            "checks": {
                "worker_registered": True,
                "dispatch_pipeline_ready": True,
                "dispatch_claimable_ready": True,
            },
            "timing": {"worker_registered_ms": 0},
            "cycle_id": "default-cycle",
        }
        self._snapshots = list(snapshots or [default_snapshot])
        self._last_snapshot = dict(self._snapshots[-1]) if self._snapshots else {}

    def record_boot_event(self, stage: str, **details):
        self.events.append((stage, dict(details)))

    def mark_first_token_issued(self, *, room_name: str):
        self.events.append(("first_token_issued", {"room": room_name}))

    def snapshot(self) -> dict:
        if self._snapshots:
            self._last_snapshot = dict(self._snapshots.pop(0))
        return dict(self._last_snapshot)

    def mark_dispatch_created(self, *, room_name: str, agent_name: str):
        self.events.append(
            ("dispatch_created", {"room": room_name, "agent_name": agent_name})
        )

    def mark_dispatch_pipeline_ready(self, *, source: str):
        self.events.append(("dispatch_pipeline_ready", {"source": source}))


@pytest.mark.asyncio
async def test_handle_token_retries_transient_dispatch_error_once(monkeypatch, unused_tcp_port: int) -> None:
    attempts = 0
    tracker = _FakeTracker()

    async def _flaky_dispatch(_room_name: str):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError(
                "Cannot connect to host onetry-embmzlra.livekit.cloud:443 ssl:default [Temporary failure in name resolution]"
            )

    monkeypatch.setattr(handlers, "_ensure_room_dispatch", _flaky_dispatch)
    monkeypatch.setattr(handlers, "AccessToken", _FakeAccessToken)
    monkeypatch.setattr(handlers, "get_runtime_readiness_tracker", lambda: tracker)
    monkeypatch.setenv("LIVEKIT_API_KEY", "k")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "s")
    monkeypatch.setenv("LIVEKIT_URL", "https://example.livekit.cloud")
    monkeypatch.setenv("MAYA_TOKEN_DISPATCH_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("MAYA_TOKEN_DISPATCH_RETRY_DELAY_S", "0")

    app = web.Application()
    app.router.add_post("/token", handlers.handle_token)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/token",
            {"roomName": "room-a", "participantName": "participant-a"},
        )
    finally:
        await runner.cleanup()

    assert status == 200
    assert body["token"] == "fake-jwt"
    assert attempts == 2
    stages = [stage for stage, _details in tracker.events]
    assert "token_request_retry_scheduled" in stages
    assert "token_request_success" in stages
    retry_details = next(details for stage, details in tracker.events if stage == "token_request_retry_scheduled")
    success_details = next(details for stage, details in tracker.events if stage == "token_request_success")
    assert retry_details["attempt"] == 1
    assert success_details["dispatch_attempts"] == 2


@pytest.mark.asyncio
async def test_handle_token_success_records_single_dispatch_attempt(monkeypatch, unused_tcp_port: int) -> None:
    attempts = 0
    tracker = _FakeTracker()

    async def _ok_dispatch(_room_name: str):
        nonlocal attempts
        attempts += 1

    monkeypatch.setattr(handlers, "_ensure_room_dispatch", _ok_dispatch)
    monkeypatch.setattr(handlers, "AccessToken", _FakeAccessToken)
    monkeypatch.setattr(handlers, "get_runtime_readiness_tracker", lambda: tracker)
    monkeypatch.setenv("LIVEKIT_API_KEY", "k")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "s")
    monkeypatch.setenv("LIVEKIT_URL", "https://example.livekit.cloud")
    monkeypatch.setenv("MAYA_TOKEN_DISPATCH_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("MAYA_TOKEN_DISPATCH_RETRY_DELAY_S", "0")

    app = web.Application()
    app.router.add_post("/token", handlers.handle_token)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/token",
            {"roomName": "room-a", "participantName": "participant-a"},
        )
    finally:
        await runner.cleanup()

    assert status == 200
    assert body["token"] == "fake-jwt"
    assert attempts == 1
    success_details = next(details for stage, details in tracker.events if stage == "token_request_success")
    assert success_details["dispatch_attempts"] == 1


@pytest.mark.asyncio
async def test_handle_token_does_not_retry_non_transient_dispatch_error(monkeypatch, unused_tcp_port: int) -> None:
    attempts = 0
    tracker = _FakeTracker()

    async def _bad_dispatch(_room_name: str):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("dispatch failed permanently")

    monkeypatch.setattr(handlers, "_ensure_room_dispatch", _bad_dispatch)
    monkeypatch.setattr(handlers, "get_runtime_readiness_tracker", lambda: tracker)
    monkeypatch.setenv("MAYA_TOKEN_DISPATCH_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("MAYA_TOKEN_DISPATCH_RETRY_DELAY_S", "0")

    app = web.Application()
    app.router.add_post("/token", handlers.handle_token)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/token",
            {"roomName": "room-a", "participantName": "participant-a"},
        )
    finally:
        await runner.cleanup()

    assert status == 500
    assert body["error"] == "dispatch failed permanently"
    assert attempts == 1
    stages = [stage for stage, _details in tracker.events]
    assert "token_request_retry_scheduled" not in stages
    assert "token_request_failed" in stages


@pytest.mark.asyncio
async def test_handle_token_returns_warming_up_when_first_turn_gate_closed(monkeypatch, unused_tcp_port: int) -> None:
    tracker = _FakeTracker(
        snapshots=[
            {
                "ready": False,
                "state": "WORKER_CONNECTING",
                "checks": {
                    "worker_registered": False,
                    "dispatch_pipeline_ready": False,
                    "dispatch_claimable_ready": False,
                },
                "timing": {"worker_registered_ms": None},
                "cycle_id": "cycle-a",
            }
        ]
    )

    async def _unexpected_dispatch(_room_name: str) -> None:
        raise AssertionError("_ensure_room_dispatch should not run while warming up")

    monkeypatch.setattr(handlers, "_ensure_room_dispatch", _unexpected_dispatch)
    monkeypatch.setattr(handlers, "get_runtime_readiness_tracker", lambda: tracker)

    app = web.Application()
    app.router.add_post("/token", handlers.handle_token)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/token",
            {"roomName": "room-a", "participantName": "participant-a"},
        )
    finally:
        await runner.cleanup()

    assert status == 503
    assert body["error"] == "warming_up"
    assert body["retry_after_ms"] == 1000
    assert body["details"]["state"] == "WORKER_CONNECTING"
    assert body["details"]["cycle_id"] == "cycle-a"


@pytest.mark.asyncio
async def test_handle_token_succeeds_if_gate_clears_within_bounded_wait(monkeypatch, unused_tcp_port: int) -> None:
    tracker = _FakeTracker(
        snapshots=[
            {
                "ready": False,
                "state": "WORKER_CONNECTING",
                "checks": {
                    "worker_registered": False,
                    "dispatch_pipeline_ready": False,
                    "dispatch_claimable_ready": False,
                },
                "timing": {"worker_registered_ms": None},
                "cycle_id": "cycle-a",
            },
            {
                "ready": True,
                "state": "READY_SESSION_CAPABLE",
                "checks": {
                    "worker_registered": True,
                    "dispatch_pipeline_ready": True,
                    "dispatch_claimable_ready": True,
                },
                "timing": {"worker_registered_ms": 1234},
                "cycle_id": "cycle-a",
            },
        ]
    )
    attempts = 0

    async def _ok_dispatch(_room_name: str) -> None:
        nonlocal attempts
        attempts += 1

    monkeypatch.setattr(handlers, "_ensure_room_dispatch", _ok_dispatch)
    monkeypatch.setattr(handlers, "AccessToken", _FakeAccessToken)
    monkeypatch.setattr(handlers, "get_runtime_readiness_tracker", lambda: tracker)
    clock = {"value": 0.0}

    async def _advance_sleep(delay: float) -> None:
        clock["value"] += delay

    monkeypatch.setattr(handlers.asyncio, "sleep", _advance_sleep)
    monkeypatch.setenv("LIVEKIT_API_KEY", "k")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "s")
    monkeypatch.setenv("LIVEKIT_URL", "https://example.livekit.cloud")
    monkeypatch.setattr(handlers.time, "monotonic", lambda: clock["value"])

    app = web.Application()
    app.router.add_post("/token", handlers.handle_token)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/token",
            {"roomName": "room-a", "participantName": "participant-a"},
        )
    finally:
        await runner.cleanup()

    assert status == 200
    assert body["token"] == "fake-jwt"
    assert attempts == 1


@pytest.mark.asyncio
async def test_handle_send_message_returns_warming_up_contract_when_runtime_not_ready(monkeypatch, unused_tcp_port: int) -> None:
    handlers._publish_token_room_context(
        room_name="room-a",
        participant_name="participant-a",
        token_status=200,
        context_state="token_issued",
    )
    tracker = _FakeTracker(
        snapshots=[
            {
                "ready": False,
                "state": "WORKER_CONNECTING",
                "checks": {
                    "worker_registered": False,
                    "dispatch_pipeline_ready": False,
                    "dispatch_claimable_ready": False,
                },
                "timing": {"worker_registered_ms": None},
                "probe": {},
                "session": {},
                "worker_alive": False,
                "last_probe_ok": False,
                "last_probe_age_ms": None,
                "cycle_id": "cycle-b",
            }
        ]
    )
    monkeypatch.setattr(handlers, "get_runtime_readiness_tracker", lambda: tracker)

    app = web.Application()
    app.router.add_post("/send_message", handlers.handle_send_message)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    try:
        status, body = await _post_json(
            f"http://127.0.0.1:{unused_tcp_port}",
            "/send_message",
            {"message": "hello", "user_id": "u1", "run_id": "run-1"},
        )
    finally:
        await runner.cleanup()

    assert status == 503
    assert body["error"] == "warming_up"
    assert body["retry_after_ms"] == 1000
    assert body["details"]["state"] == "WORKER_CONNECTING"
    assert body["details"]["cycle_id"] == "cycle-b"


@pytest.mark.asyncio
async def test_ensure_room_dispatch_uses_snapshot_worker_counts(monkeypatch) -> None:
    tracker = _FakeTracker(
        snapshots=[
            {
                "worker_alive": True,
                "state": "WORKER_CONNECTING",
                "cycle_id": "cycle-c",
                "active_worker_attempt": "attempt-c",
                "checks": {
                    "worker_registered": False,
                    "dispatch_claimable_ready": False,
                },
            }
        ]
    )

    class _FakeLKAgentDispatch:
        async def list_dispatch(self, *, room_name: str):
            return []

        async def create_dispatch(self, _request):
            return SimpleNamespace(id="dispatch-1", metadata="", state=SimpleNamespace(jobs=[]))

    class _FakeLKRoom:
        async def create_room(self, _request):
            return None

    class _FakeLiveKitAPI:
        def __init__(self, **_kwargs):
            self.agent_dispatch = _FakeLKAgentDispatch()
            self.room = _FakeLKRoom()

        async def aclose(self):
            return None

    monkeypatch.setattr(handlers, "LiveKitAPI", _FakeLiveKitAPI)
    monkeypatch.setattr(handlers, "get_runtime_readiness_tracker", lambda: tracker)
    monkeypatch.setenv("LIVEKIT_URL", "https://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "k")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "s")

    await handlers._ensure_room_dispatch("room-a")

    dispatch_requested = next(details for stage, details in tracker.events if stage == "dispatch_requested")
    assert dispatch_requested["workers_online"] == 0
    assert dispatch_requested["workers_claimable"] == 0
