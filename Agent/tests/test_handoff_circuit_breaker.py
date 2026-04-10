import time

import pytest

from core.agents.contracts import AgentCapabilityMatch, AgentHandoffRequest, AgentHandoffResult
from core.agents.handoff_manager import CircuitBreaker, HandoffManager


def _request(**overrides) -> AgentHandoffRequest:
    payload = {
        "handoff_id": "handoff-cb-1",
        "trace_id": "trace-cb-1",
        "conversation_id": "conversation-cb-1",
        "task_id": None,
        "parent_agent": "maya",
        "active_agent": "maya",
        "target_agent": "research",
        "intent": "research",
        "user_text": "who is ada lovelace",
        "context_slice": "research request",
        "execution_mode": "inline",
        "delegation_depth": 0,
        "max_depth": 1,
        "handoff_reason": "test",
        "metadata": {"user_id": "u1"},
    }
    payload.update(overrides)
    return AgentHandoffRequest(**payload)


def test_circuit_breaker_open_transition():
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=30, success_threshold=2)

    assert breaker.state == "closed"
    assert breaker.allow_request() is True

    breaker.record_failure()
    assert breaker.state == "closed"

    breaker.record_failure()
    assert breaker.state == "open"
    assert breaker.allow_request() is False


def test_circuit_breaker_half_open_probe(monkeypatch):
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=30, success_threshold=2)
    breaker.record_failure()
    assert breaker.state == "open"

    opened_at = breaker._opened_at
    assert opened_at is not None

    monkeypatch.setattr(time, "time", lambda: opened_at + 31)
    assert breaker.allow_request() is True
    assert breaker.state == "half-open"


@pytest.mark.asyncio
async def test_circuit_breaker_close_on_success():
    class _Registry:
        def __init__(self):
            self.fail = True

        async def can_accept(self, request):
            return AgentCapabilityMatch(
                agent_name=request.target_agent,
                confidence=1.0,
                reason="ok",
                hard_constraints_passed=True,
            )

        async def handle(self, request):
            if self.fail:
                raise RuntimeError("forced failure")
            return AgentHandoffResult(
                handoff_id=request.handoff_id,
                trace_id=request.trace_id,
                source_agent=request.target_agent,
                status="completed",
                user_visible_text=None,
                voice_text=None,
                structured_payload={"ok": True},
                next_action="continue",
                error_code=None,
                error_detail=None,
            )

    registry = _Registry()
    manager = HandoffManager(registry)
    manager._depth_breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0, success_threshold=2)

    failed = await manager.delegate(_request())
    assert failed.status == "failed"
    assert manager._depth_breaker.state == "open"

    registry.fail = False

    first_success = await manager.delegate(_request())
    assert first_success.status == "completed"
    assert manager._depth_breaker.state == "half-open"

    second_success = await manager.delegate(_request())
    assert second_success.status == "completed"
    assert manager._depth_breaker.state == "closed"
