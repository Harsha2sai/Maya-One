from __future__ import annotations

from types import SimpleNamespace

import pytest

from api import handlers


class _FakeAgentDispatch:
    def __init__(self, dispatches):
        self._dispatches = dispatches

    async def list_dispatch(self, *, room_name: str):
        return self._dispatches


class _FakeRoomApi:
    def __init__(self, participants):
        self._participants = participants

    async def list_participants(self, _request):
        return SimpleNamespace(participants=self._participants)


class _FakeLiveKit:
    def __init__(self, dispatches, participants):
        self.agent_dispatch = _FakeAgentDispatch(dispatches)
        self.room = _FakeRoomApi(participants)


class _FakeTracker:
    def __init__(self, stage, recent_connect_durations_ms=None, has_successful_room_join=False):
        self._stage = dict(stage)
        self._recent_connect_durations_ms = list(recent_connect_durations_ms or [])
        self._has_successful_room_join = bool(has_successful_room_join)

    def room_stage_snapshot(self, room_name: str):
        return {"room": room_name, **self._stage}

    def recent_connect_durations_ms(self, *, limit: int = 20):
        return self._recent_connect_durations_ms[-limit:]

    def has_successful_room_join(self) -> bool:
        return self._has_successful_room_join


def _dispatch(agent_name: str = "maya-one"):
    return SimpleNamespace(agent_name=agent_name, id="dispatch-1", metadata="", state=SimpleNamespace(jobs=[]))


@pytest.mark.asyncio
async def test_check_room_session_ready_reports_no_worker_claim(monkeypatch):
    monkeypatch.setattr(handlers, "get_runtime_readiness_tracker", lambda: _FakeTracker({}))
    lk = _FakeLiveKit([_dispatch()], [])

    ready, status = await handlers._check_room_session_ready(lk, "room-a")

    assert ready is False
    assert status["room_failure_class"] == "no_worker_claim"
    assert status["room_failure_reason"] == "no_worker_claim"


@pytest.mark.asyncio
async def test_check_room_session_ready_reports_worker_joining_room(monkeypatch):
    monkeypatch.setattr(
        handlers,
        "get_runtime_readiness_tracker",
        lambda: _FakeTracker(
            {
                "worker_job_claimed_at_ms": 1000,
                "room_connect_started_at_ms": 1100,
            }
        ),
    )
    lk = _FakeLiveKit([_dispatch()], [])

    ready, status = await handlers._check_room_session_ready(lk, "room-a")

    assert ready is False
    assert status["room_failure_class"] == "worker_connecting"
    assert status["room_failure_reason"] == "worker_connecting"


@pytest.mark.asyncio
async def test_check_room_session_ready_reports_room_joining_after_connect(monkeypatch):
    monkeypatch.setattr(
        handlers,
        "get_runtime_readiness_tracker",
        lambda: _FakeTracker(
            {
                "worker_job_claimed_at_ms": 1000,
                "room_connect_started_at_ms": 1100,
                "room_connect_success_at_ms": 1300,
            }
        ),
    )
    lk = _FakeLiveKit([_dispatch()], [])

    ready, status = await handlers._check_room_session_ready(lk, "room-a")

    assert ready is False
    assert status["room_failure_class"] == "room_joining"
    assert status["room_failure_reason"] == "room_joining"


@pytest.mark.asyncio
async def test_check_room_session_ready_reports_session_booting(monkeypatch):
    monkeypatch.setattr(
        handlers,
        "get_runtime_readiness_tracker",
        lambda: _FakeTracker(
            {
                "worker_job_claimed_at_ms": 1000,
                "room_connect_started_at_ms": 1100,
                "room_connect_success_at_ms": 1300,
                "room_joined_at_ms": 1400,
            }
        ),
    )
    lk = _FakeLiveKit([_dispatch()], [SimpleNamespace(identity="agent-test")])

    ready, status = await handlers._check_room_session_ready(lk, "room-a")

    assert ready is False
    assert status["room_failure_class"] == "session_booting"
    assert status["room_failure_reason"] == "session_booting"


@pytest.mark.asyncio
async def test_wait_for_room_session_ready_uses_deadline(monkeypatch):
    attempts = 0

    async def _fake_check(_lk, _room_name):
        nonlocal attempts
        attempts += 1
        return False, {
            "dispatch_ready": True,
            "agent_present": False,
            "participant_count": 0,
            "room_failure_class": "room_joining",
            "room_failure_reason": "room_joining",
            "room_stage": {
                "worker_job_claimed_at_ms": 1000,
                "room_connect_started_at_ms": 1001,
                "room_connect_success_at_ms": 1200,
            },
        }

    monkeypatch.setattr(handlers, "_check_room_session_ready", _fake_check)

    ready, status = await handlers._wait_for_room_session_ready(
        object(),
        "room-a",
        wait_budget_s=0.08,
        interval_s=0.01,
    )

    assert ready is False
    assert attempts >= 2
    assert status["attempt_index"] == attempts
    assert status["attempts"] == attempts
    assert status["elapsed_ms"] >= 60
    assert status["wait_budget_ms"] == 80


@pytest.mark.asyncio
async def test_wait_for_room_session_ready_applies_first_turn_grace_and_succeeds(monkeypatch):
    attempts = 0

    async def _fake_check(_lk, _room_name):
        nonlocal attempts
        attempts += 1
        if attempts >= 3:
            return True, {
                "dispatch_ready": True,
                "agent_present": True,
                "participant_count": 1,
                "room_failure_class": "",
                "room_failure_reason": "",
                "room_stage": {
                    "worker_job_claimed_at_ms": 1000,
                    "room_joined_at_ms": 1200,
                    "session_started_at_ms": 1300,
                    "session_ready_at_ms": 1600,
                },
            }
        return False, {
            "dispatch_ready": True,
            "agent_present": True,
            "participant_count": 1,
            "room_failure_class": "session_booting",
            "room_failure_reason": "session_booting",
            "room_stage": {
                "worker_job_claimed_at_ms": 1000,
                "room_joined_at_ms": 1200,
                "session_started_at_ms": 1300,
                "session_ready_at_ms": None,
            },
        }

    monkeypatch.setattr(handlers, "_check_room_session_ready", _fake_check)
    monkeypatch.setenv("MAYA_SEND_MESSAGE_FIRST_TURN_GRACE_S", "0.05")
    monkeypatch.setenv("MAYA_SEND_MESSAGE_FIRST_TURN_GRACE_POLL_INTERVAL_S", "0.01")

    ready, status = await handlers._wait_for_room_session_ready(
        object(),
        "room-a",
        wait_budget_s=0.01,
        interval_s=0.01,
    )

    assert ready is True
    assert attempts >= 3
    assert status["first_turn_grace_applied"] is True
    assert status["first_turn_grace_attempts"] >= 1
    assert status["first_request_arrived_at_ms"] is not None
    assert status["first_request_released_at_ms"] is not None
    assert status["session_ready_at_ms"] == 1600


@pytest.mark.asyncio
async def test_wait_for_room_session_ready_fails_after_first_turn_grace_exhausted(monkeypatch):
    attempts = 0

    async def _fake_check(_lk, _room_name):
        nonlocal attempts
        attempts += 1
        return False, {
            "dispatch_ready": True,
            "agent_present": True,
            "participant_count": 1,
            "room_failure_class": "session_booting",
            "room_failure_reason": "session_booting",
            "room_stage": {
                "worker_job_claimed_at_ms": 1000,
                "room_joined_at_ms": 1200,
                "session_started_at_ms": 1300,
                "session_ready_at_ms": None,
            },
        }

    monkeypatch.setattr(handlers, "_check_room_session_ready", _fake_check)
    monkeypatch.setenv("MAYA_SEND_MESSAGE_FIRST_TURN_GRACE_S", "0.03")
    monkeypatch.setenv("MAYA_SEND_MESSAGE_FIRST_TURN_GRACE_POLL_INTERVAL_S", "0.01")

    ready, status = await handlers._wait_for_room_session_ready(
        object(),
        "room-a",
        wait_budget_s=0.01,
        interval_s=0.01,
    )

    assert ready is False
    assert attempts >= 2
    assert status["first_turn_grace_applied"] is True
    assert status["first_turn_grace_attempts"] >= 1
    assert status["first_turn_grace_elapsed_ms"] >= 0
    assert status["first_request_arrived_at_ms"] is not None
    assert status["first_request_released_at_ms"] is not None


def test_static_send_message_wait_budget_uses_cold_budget_before_any_success(monkeypatch):
    monkeypatch.setenv("MAYA_SEND_MESSAGE_COLD_ROOM_WAIT_S", "35")
    monkeypatch.setenv("MAYA_SEND_MESSAGE_WARM_ROOM_WAIT_S", "25")

    tracker = _FakeTracker({}, has_successful_room_join=False)

    budget = handlers._static_send_message_wait_budget(tracker)

    assert float(budget["wait_budget_s"]) == 35.0
    assert budget["room_wait_budget_source"] == "cold_static"
    assert int(budget["successful_room_join_count"]) == 0


def test_static_send_message_wait_budget_uses_warm_budget_after_success(monkeypatch):
    monkeypatch.setenv("MAYA_SEND_MESSAGE_COLD_ROOM_WAIT_S", "35")
    monkeypatch.setenv("MAYA_SEND_MESSAGE_WARM_ROOM_WAIT_S", "25")

    tracker = _FakeTracker({}, has_successful_room_join=True)

    budget = handlers._static_send_message_wait_budget(tracker)

    assert float(budget["wait_budget_s"]) == 25.0
    assert budget["room_wait_budget_source"] == "warm_static"
    assert int(budget["successful_room_join_count"]) == 1
