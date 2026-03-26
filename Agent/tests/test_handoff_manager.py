from types import SimpleNamespace

import pytest

from core.agents.contracts import AgentCapabilityMatch, AgentHandoffRequest, AgentHandoffResult, HandoffSignal
from core.agents.handoff_manager import HandoffManager, HandoffValidationError, get_handoff_manager
from core.agents.registry import AgentRegistry


def _request(**overrides) -> AgentHandoffRequest:
    payload = {
        "handoff_id": "handoff-1",
        "trace_id": "trace-1",
        "conversation_id": "conversation-1",
        "task_id": None,
        "parent_agent": "maya",
        "active_agent": "maya",
        "target_agent": "research",
        "intent": "research",
        "user_text": "who is the current prime minister of japan",
        "context_slice": "User asked a research question.",
        "execution_mode": "inline",
        "delegation_depth": 0,
        "max_depth": 1,
        "handoff_reason": "test",
        "metadata": {"user_id": "u1"},
    }
    payload.update(overrides)
    return AgentHandoffRequest(**payload)


@pytest.mark.asyncio
async def test_invalid_parent_is_blocked():
    manager = HandoffManager(AgentRegistry())
    result = await manager.delegate(_request(parent_agent="planner"))
    assert result.status == "failed"
    assert result.error_code == "HandoffValidationError"


def test_background_handoff_requires_task_id():
    manager = HandoffManager(AgentRegistry())
    with pytest.raises(HandoffValidationError):
        manager.validate_request(_request(execution_mode="background", task_id=None))


def test_signal_maps_to_target():
    manager = HandoffManager(AgentRegistry())
    signal = HandoffSignal(
        signal_name="transfer_to_planner",
        reason="planning required",
        execution_mode="planning",
        context_hint="plan it",
    )
    assert manager.consume_signal(signal) == "planner"


def test_get_handoff_manager_returns_fresh_instance():
    manager_one = get_handoff_manager(AgentRegistry())
    manager_two = get_handoff_manager(AgentRegistry())
    assert manager_one is not manager_two


@pytest.mark.asyncio
async def test_depth_guard_blocks_subagent_delegation():
    manager = HandoffManager(AgentRegistry())
    result = await manager.delegate(
        _request(
            parent_agent="research",
            active_agent="research",
            target_agent="planner",
            execution_mode="planning",
            task_id="task-1",
            delegation_depth=1,
        )
    )
    assert result.status == "failed"
    assert result.error_code == "HandoffValidationError"
    assert any(
        token in str(result.error_detail or "")
        for token in ("parent_agent must be maya", "delegation depth exceeded")
    )


@pytest.mark.asyncio
async def test_zero_confidence_handoff_is_logged_and_allowed(caplog):
    class _Registry:
        async def can_accept(self, request):
            return AgentCapabilityMatch(
                agent_name=request.target_agent,
                confidence=0.0,
                reason="rewritten_followup_keyword_sparse",
                hard_constraints_passed=True,
            )

        async def handle(self, request):
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

    manager = HandoffManager(_Registry())
    with caplog.at_level("INFO"):
        result = await manager.delegate(_request())

    assert result.status == "completed"
    assert "handoff_zero_confidence_allowed" in caplog.text
