import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.agents.contracts import AgentHandoffRequest, HandoffSignal
from core.agents.handoff_manager import HandoffManager, HandoffValidationError, get_handoff_manager
from core.agents.registry import AgentRegistry
from core.context.context_builder import ContextBuilder
from core.agents.system_operator_agent import SystemOperatorAgent
from core.context.role_context_builders.worker_context_builder import WorkerContextBuilder
from core.llm.llm_roles import CHAT_CONFIG, PLANNER_CONFIG, TOOL_ROUTER_CONFIG, WORKER_CONFIG
from core.orchestrator.agent_orchestrator import AgentOrchestrator
from core.prompts import (
    get_maya_primary_prompt,
    get_planner_prompt,
    get_tool_router_prompt,
    get_worker_prompt,
)
from core.system.host_capability_profile import (
    collect_host_capability_profile,
    refresh_host_capability_profile,
)
from prompts import AGENT_INSTRUCTION


def _request(**overrides) -> AgentHandoffRequest:
    payload = {
        "handoff_id": "h-1",
        "trace_id": "t-1",
        "conversation_id": "c-1",
        "task_id": None,
        "parent_agent": "maya",
        "active_agent": "maya",
        "target_agent": "research",
        "intent": "research",
        "user_text": "who is the ceo of openai",
        "context_slice": "User asked a research question.",
        "execution_mode": "inline",
        "delegation_depth": 0,
        "max_depth": 1,
        "handoff_reason": "test",
        "metadata": {"user_id": "u1"},
    }
    payload.update(overrides)
    return AgentHandoffRequest(**payload)


def test_prompt_authority_is_canonical():
    assert CHAT_CONFIG.system_prompt_template == get_maya_primary_prompt()
    assert PLANNER_CONFIG.system_prompt_template == get_planner_prompt()
    assert TOOL_ROUTER_CONFIG.system_prompt_template == get_tool_router_prompt()
    assert WORKER_CONFIG.system_prompt_template == get_worker_prompt()
    assert AGENT_INSTRUCTION == get_maya_primary_prompt()


def test_worker_context_builder_uses_research_overlay():
    task = SimpleNamespace(description="Research a topic")
    step = SimpleNamespace(description="Find sources", worker="research")
    chat_ctx = WorkerContextBuilder.build(task, step)
    messages = chat_ctx.messages() if callable(chat_ctx.messages) else chat_ctx.messages
    system_message = messages[0]
    content = system_message.content[0] if isinstance(system_message.content, list) else system_message.content
    assert "Research worker overlay" in content


@pytest.mark.asyncio
async def test_context_builder_chat_mode_uses_canonical_maya_prompt():
    memory_manager = SimpleNamespace(get_user_context=AsyncMock(return_value=""))
    builder = ContextBuilder(llm=None, memory_manager=memory_manager, user_id="u1")
    builder.task_manager.get_active_tasks = AsyncMock(return_value=[])

    messages, tools = await builder("hello there", SimpleNamespace(messages=[]))

    system_message = messages[0]
    content = system_message.content[0] if isinstance(system_message.content, list) else system_message.content
    assert "You are Maya" in content
    assert "Conversation mode:" in content
    assert tools == []


@pytest.mark.asyncio
async def test_handoff_manager_blocks_invalid_parent():
    manager = HandoffManager(AgentRegistry())
    request = _request(parent_agent="planner")
    result = await manager.delegate(request)
    assert result.status == "failed"
    assert result.error_code == "HandoffValidationError"


@pytest.mark.asyncio
async def test_handoff_manager_blocks_depth_exceeded():
    manager = HandoffManager(AgentRegistry())
    request = _request(delegation_depth=1)
    result = await manager.delegate(request)
    assert result.status == "failed"
    assert result.error_code == "HandoffValidationError"


def test_handoff_manager_requires_task_id_for_background():
    manager = HandoffManager(AgentRegistry())
    request = _request(execution_mode="background", task_id=None)
    with pytest.raises(HandoffValidationError):
        manager.validate_request(request)


def test_handoff_signal_maps_to_target_and_logs(caplog):
    manager = HandoffManager(AgentRegistry())
    signal = HandoffSignal(
        signal_name="transfer_to_planner",
        reason="needs planning",
        execution_mode="planning",
        context_hint="plan it",
    )
    with caplog.at_level(logging.INFO):
        target = manager.consume_signal(signal)
    assert target == "planner"
    assert "handoff_signal_consumed" in caplog.text


def test_get_handoff_manager_refreshes_for_new_registry():
    manager_one = get_handoff_manager(AgentRegistry())
    manager_two = get_handoff_manager(AgentRegistry())
    assert manager_one is not manager_two


@pytest.mark.asyncio
async def test_system_operator_contract_returns_intent_only():
    agent = SystemOperatorAgent()
    request = _request(
        target_agent="system_operator",
        user_text="take a screenshot",
        intent="system",
    )
    result = await agent.handle(request)
    assert result.status == "completed"
    assert result.structured_payload["action_type"] == "SCREENSHOT"
    assert result.next_action == "continue"


def test_host_capability_profile_collect_and_refresh():
    profile = collect_host_capability_profile(runtime_mode="worker")
    assert profile.cpu_count >= 1
    refreshed = refresh_host_capability_profile(profile)
    assert refreshed.os == profile.os
    assert refreshed.cpu_count == profile.cpu_count


@pytest.mark.asyncio
async def test_research_route_consumes_signal_and_delegates(monkeypatch):
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._handoff_manager.consume_signal = MagicMock(return_value="research")
    orchestrator._handoff_manager.delegate = AsyncMock(return_value=SimpleNamespace(status="completed", error_code=None))
    orchestrator._run_research_background = AsyncMock()

    response = await orchestrator._handle_research_route(
        message="research openai",
        user_id="u1",
        tool_context=SimpleNamespace(session_id="s1", trace_id="trace-1", room=None, task_id=None, conversation_id="c1"),
    )

    orchestrator._handoff_manager.consume_signal.assert_called_once()
    orchestrator._handoff_manager.delegate.assert_awaited_once()
    assert response.structured_data["_routing_mode_type"] == "research_pending"


@pytest.mark.asyncio
async def test_task_request_includes_host_profile_in_planner_input():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._handoff_manager.consume_signal = MagicMock(return_value="planner")
    orchestrator._handoff_manager.delegate = AsyncMock(return_value=SimpleNamespace(status="completed", error_code=None))
    orchestrator._get_host_capability_profile = MagicMock(
        return_value={
            "os": "linux",
            "machine": "x86_64",
            "cpu_count": 8,
            "ram_total_gb": 16.0,
            "ram_available_gb": 8.0,
            "disk_free_gb": 120.0,
            "gpu_present": False,
            "gpu_name": None,
            "runtime_mode": "voice",
            "safety_budget": "standard",
        }
    )
    orchestrator._retrieve_memory_context_async = AsyncMock(return_value="")
    orchestrator.planning_engine.generate_plan_result = None
    orchestrator.planning_engine.generate_plan = AsyncMock(return_value=[])

    response = await orchestrator._handle_task_request(
        "plan a local data backup workflow",
        user_id="u1",
    )

    planner_input = orchestrator.planning_engine.generate_plan.await_args.args[0]
    assert "Host Capability Profile:" in planner_input
    assert "cpu_count=8" in planner_input
    assert "ram_available_gb=8.0" in planner_input
    assert "couldn't create a plan" in response.lower()


@pytest.mark.asyncio
async def test_system_route_delegates_before_live_system_execution():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="system")
    orchestrator._handoff_manager.consume_signal = MagicMock(return_value="system_operator")
    orchestrator._handoff_manager.delegate = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            error_code=None,
            user_visible_text=None,
            structured_payload={"action_type": "SCREENSHOT", "tool_name": "take_screenshot"},
        )
    )
    orchestrator._get_host_capability_profile = MagicMock(return_value={"os": "linux", "cpu_count": 8})
    fake_system_agent = MagicMock()
    fake_system_agent.run = AsyncMock(
        return_value=SimpleNamespace(
            success=True,
            action_type=SimpleNamespace(value="SCREENSHOT"),
            message="Saved screenshot.",
            detail="/tmp/test.png",
            rollback_available=False,
            trace_id="trace-system",
        )
    )
    orchestrator._resolve_system_agent = MagicMock(return_value=fake_system_agent)

    response = await orchestrator._handle_chat_response(
        "take a screenshot",
        user_id="u1",
        origin="chat",
    )

    orchestrator._handoff_manager.consume_signal.assert_called_once()
    orchestrator._handoff_manager.delegate.assert_awaited_once()
    fake_system_agent.run.assert_awaited_once()
    request = orchestrator._handoff_manager.delegate.await_args.args[0]
    assert request.target_agent == "system_operator"
    assert request.metadata["host_profile"]["cpu_count"] == 8
    assert response.display_text == "Saved screenshot."


@pytest.mark.asyncio
async def test_system_route_supports_photograph_synonym():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="system")
    orchestrator._handoff_manager.consume_signal = MagicMock(return_value="system_operator")
    orchestrator._handoff_manager.delegate = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            error_code=None,
            user_visible_text=None,
            structured_payload={"action_type": "SCREENSHOT", "tool_name": "take_screenshot"},
        )
    )
    orchestrator._get_host_capability_profile = MagicMock(return_value={"os": "linux", "cpu_count": 8})
    fake_system_agent = MagicMock()
    fake_system_agent.run = AsyncMock(
        return_value=SimpleNamespace(
            success=True,
            action_type=SimpleNamespace(value="SCREENSHOT"),
            message="Saved screenshot.",
            detail="/tmp/test.png",
            rollback_available=False,
            trace_id="trace-system",
        )
    )
    orchestrator._resolve_system_agent = MagicMock(return_value=fake_system_agent)

    response = await orchestrator._handle_chat_response(
        "take a photograph",
        user_id="u1",
        origin="chat",
    )

    orchestrator._handoff_manager.delegate.assert_awaited_once()
    fake_system_agent.run.assert_awaited_once()
    assert response.display_text == "Saved screenshot."


@pytest.mark.asyncio
async def test_system_route_handoff_failure_falls_back_to_legacy_execution():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    orchestrator._router = MagicMock()
    orchestrator._router.route = AsyncMock(return_value="system")
    orchestrator._handoff_manager.consume_signal = MagicMock(return_value="system_operator")
    orchestrator._handoff_manager.delegate = AsyncMock(
        return_value=SimpleNamespace(
            status="failed",
            error_code="system_intent_unresolved",
            user_visible_text="I couldn't determine a safe system action for that request.",
            structured_payload={},
        )
    )
    fake_system_agent = MagicMock()
    fake_system_agent.run = AsyncMock(
        return_value=SimpleNamespace(
            success=True,
            action_type=SimpleNamespace(value="FILE_DELETE"),
            message="Legacy system route handled.",
            detail="ok",
            rollback_available=False,
            trace_id="trace-system-fallback",
        )
    )
    orchestrator._resolve_system_agent = MagicMock(return_value=fake_system_agent)

    response = await orchestrator._handle_chat_response(
        "delete the file test.txt",
        user_id="u1",
        origin="chat",
    )

    orchestrator._resolve_system_agent.assert_called_once()
    fake_system_agent.run.assert_awaited_once()
    assert response.display_text == "Legacy system route handled."
