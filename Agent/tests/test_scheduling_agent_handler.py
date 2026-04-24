from types import SimpleNamespace

import pytest

from core.agents.contracts import AgentCapabilityMatch, AgentHandoffResult
from core.agents.handoff_manager import HandoffManager
from core.agents.scheduling_agent_handler import SchedulingAgentHandler


def _request(**overrides):
    payload = {
        "handoff_id": "handoff-scheduling-1",
        "trace_id": "trace-scheduling-1",
        "conversation_id": "conversation-1",
        "task_id": None,
        "parent_agent": "maya",
        "active_agent": "maya",
        "target_agent": "scheduling",
        "intent": "scheduling",
        "user_text": "set a reminder to drink water in 20 minutes",
        "context_slice": "User asked for scheduling help.",
        "execution_mode": "inline",
        "delegation_depth": 0,
        "max_depth": 1,
        "handoff_reason": "router_scheduling",
        "metadata": {"user_id": "u1"},
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


@pytest.mark.asyncio
async def test_scheduling_handler_can_handle_scheduling_intent():
    handler = SchedulingAgentHandler()
    match = await handler.can_accept(_request())
    assert match.confidence == 1.0
    assert match.reason == "scheduling_intent"


@pytest.mark.asyncio
async def test_scheduling_handler_cannot_handle_research_intent():
    handler = SchedulingAgentHandler()
    match = await handler.can_accept(_request(intent="research", target_agent="research"))
    assert match.confidence == 0.0
    assert match.reason == "intent_not_scheduling"


@pytest.mark.asyncio
async def test_scheduling_handler_set_reminder_returns_correct_parameters():
    handler = SchedulingAgentHandler()
    result = await handler.handle(_request(user_text="set a reminder to drink water in 20 minutes"))
    assert result.status == "completed"
    assert result.structured_payload["tool_name"] == "set_reminder"
    assert result.structured_payload["parameters"] == {"text": "drink water", "time": "in 20 minutes"}


@pytest.mark.asyncio
async def test_scheduling_handler_missing_time_returns_needs_followup(monkeypatch):
    monkeypatch.setenv("SCHEDULING_MEMORY_ENRICHMENT", "false")
    handler = SchedulingAgentHandler()
    result = await handler.handle(_request(user_text="remind me to call John"))
    assert result.status == "needs_followup"
    assert result.structured_payload["clarification"] == "When would you like to be reminded?"


@pytest.mark.asyncio
async def test_scheduling_handler_missing_task_returns_needs_followup():
    handler = SchedulingAgentHandler()
    result = await handler.handle(_request(user_text="set a reminder for tomorrow"))
    assert result.status == "needs_followup"
    assert result.structured_payload["missing_slot"] == "task"
    assert result.structured_payload["parameters"]["time"] == "tomorrow"
    assert result.structured_payload["clarification"] == "What should I remind you about?"


@pytest.mark.asyncio
async def test_scheduling_handler_time_only_12h_missing_task_returns_needs_followup():
    handler = SchedulingAgentHandler()
    result = await handler.handle(_request(user_text="set a reminder for 6pm"))
    assert result.status == "needs_followup"
    assert result.structured_payload["missing_slot"] == "task"
    assert result.structured_payload["parameters"]["time"] == "6pm"
    assert result.structured_payload["clarification"] == "What should I remind you about?"


@pytest.mark.asyncio
async def test_scheduling_handler_time_only_24h_missing_task_returns_needs_followup():
    handler = SchedulingAgentHandler()
    result = await handler.handle(_request(user_text="set a reminder at 18:00"))
    assert result.status == "needs_followup"
    assert result.structured_payload["missing_slot"] == "task"
    assert result.structured_payload["parameters"]["time"] == "18:00"
    assert result.structured_payload["clarification"] == "What should I remind you about?"


@pytest.mark.asyncio
async def test_scheduling_handler_followup_query_bypasses_create_parser():
    handler = SchedulingAgentHandler()
    result = await handler.handle(_request(user_text="reminder uh what did I set"))
    assert result.status == "completed"
    assert result.structured_payload["action_type"] == "list_reminders"
    assert result.structured_payload["tool_name"] == "list_reminders"


@pytest.mark.asyncio
async def test_scheduling_handler_set_alarm_returns_correct_parameters():
    handler = SchedulingAgentHandler()
    result = await handler.handle(_request(user_text="set an alarm for 7 am", target_agent="scheduling"))
    assert result.status == "completed"
    assert result.structured_payload["tool_name"] == "set_alarm"
    assert result.structured_payload["parameters"]["time"] == "7 am"


@pytest.mark.asyncio
async def test_scheduling_handler_list_reminders_requires_no_parameters():
    handler = SchedulingAgentHandler()
    result = await handler.handle(_request(user_text="list reminders"))
    assert result.status == "completed"
    assert result.structured_payload["tool_name"] == "list_reminders"
    assert result.structured_payload["parameters"] == {}


@pytest.mark.asyncio
async def test_scheduling_handler_preserves_trace_id_and_handoff_id():
    handler = SchedulingAgentHandler()
    result = await handler.handle(_request(handoff_id="h-1", trace_id="t-1"))
    assert result.handoff_id == "h-1"
    assert result.trace_id == "t-1"


@pytest.mark.asyncio
async def test_handoff_manager_routes_scheduling_to_scheduling_handler():
    class _Registry:
        async def can_accept(self, request):
            return AgentCapabilityMatch(
                agent_name="scheduling",
                confidence=1.0,
                reason="scheduling_intent",
                hard_constraints_passed=True,
            )

        async def handle(self, request):
            return AgentHandoffResult(
                handoff_id=request.handoff_id,
                trace_id=request.trace_id,
                source_agent="scheduling",
                status="completed",
                user_visible_text="I've set a reminder.",
                voice_text="I've set a reminder.",
                structured_payload={
                    "action_type": "set_reminder",
                    "tool_name": "set_reminder",
                    "parameters": {"text": "drink water", "time": "in 20 minutes"},
                },
                next_action="respond",
            )

    manager = HandoffManager(_Registry())
    result = await manager.delegate(_request())
    assert result.status == "completed"
    assert result.source_agent == "scheduling"
