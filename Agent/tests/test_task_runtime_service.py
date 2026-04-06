from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.governance.types import UserRole
from core.orchestrator.agent_orchestrator import AgentOrchestrator
from core.response.agent_response import ToolInvocation
from core.research.research_models import ResearchResult, SourceItem
from core.tasks.task_models import TaskStep


@pytest.fixture
def orchestrator():
    agent = MagicMock()
    agent.smart_llm = None
    orch = AgentOrchestrator(MagicMock(), agent)
    orch._handoff_manager.consume_signal = MagicMock(return_value="planner")
    orch._handoff_manager.delegate = AsyncMock(return_value=SimpleNamespace(status="completed", error_code=None))
    orch._get_host_capability_profile = MagicMock(return_value={"os": "linux", "cpu_count": 8})
    orch._retrieve_memory_context_async = AsyncMock(return_value="")
    orch._announce = AsyncMock()
    return orch


@pytest.mark.asyncio
async def test_task_runtime_service_task_creation_success(orchestrator):
    orchestrator.planning_engine.generate_plan_result = None
    orchestrator.planning_engine.generate_plan = AsyncMock(
        return_value=[TaskStep(description="Step 1", worker="general")]
    )
    orchestrator.task_store.create_task = AsyncMock(return_value=True)
    orchestrator._ensure_task_worker = AsyncMock(return_value=None)
    orchestrator.memory.store_conversation_turn = AsyncMock(return_value=None)

    response = await orchestrator._handle_task_request("plan weekly goals", "u1")

    assert "started a task" in response.lower()
    orchestrator.task_store.create_task.assert_awaited_once()
    orchestrator._ensure_task_worker.assert_awaited_once_with("u1")


@pytest.mark.asyncio
async def test_task_runtime_service_planner_failure_emits_event(orchestrator):
    plan_result = type(
        "PlanResult",
        (),
        {
            "steps": [],
            "plan_failed": True,
            "error_payload": {"attempt_count": 2, "issues": ["bad_json"]},
        },
    )()
    orchestrator.planning_engine.generate_plan_result = AsyncMock(return_value=plan_result)
    orchestrator.task_store.create_task = AsyncMock(return_value=True)
    orchestrator.task_store.add_log = AsyncMock(return_value=True)
    orchestrator._handle_task_worker_event = AsyncMock(return_value=None)

    response = await orchestrator._handle_task_request("plan this", "u1")

    assert "couldn't create a safe executable plan" in response.lower()
    orchestrator.task_store.add_log.assert_awaited_once()
    orchestrator._handle_task_worker_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_task_runtime_service_report_export_requires_trusted_role(orchestrator):
    response = await orchestrator._try_handle_report_export_task(
        user_text="make a full report and save it in my downloads",
        user_id="u1",
        tool_context=SimpleNamespace(user_role=UserRole.USER),
    )

    assert response is not None
    assert "trusted role" in response.lower()


@pytest.mark.asyncio
async def test_task_runtime_service_report_export_success(orchestrator):
    orchestrator._run_inline_research_pipeline = AsyncMock(
        return_value=ResearchResult(
            summary="Detailed research summary.",
            voice_summary="Detailed voice summary.",
            sources=[
                SourceItem.from_values(
                    title="Source A",
                    url="https://example.com/source-a",
                    snippet="Snippet A",
                    provider="tavily",
                )
            ],
            query="report topic",
            trace_id="trace-report",
            duration_ms=20,
            voice_mode="deep",
        )
    )
    orchestrator._execute_tool_call = AsyncMock(
        return_value=(
            {"success": True, "message": "Created Word document"},
            ToolInvocation(tool_name="create_docx", status="success", latency_ms=4),
        )
    )

    response = await orchestrator._try_handle_report_export_task(
        user_text="create a detailed report and save it to my downloads",
        user_id="u1",
        tool_context=SimpleNamespace(user_role=UserRole.TRUSTED, session_id="s1", trace_id="t1"),
    )

    assert "saved it to ~/Downloads/" in response
    assert orchestrator._execute_tool_call.await_count == 1


@pytest.mark.asyncio
async def test_task_runtime_service_ensure_worker_idempotent():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    existing = MagicMock()
    existing.is_running = True
    existing.set_room = MagicMock()
    orchestrator.room = MagicMock()
    orchestrator._task_workers["u1"] = existing

    with patch("core.tasks.task_worker.TaskWorker") as worker_cls:
        await orchestrator._ensure_task_worker("u1")

    existing.set_room.assert_called_once_with(orchestrator.room)
    worker_cls.assert_not_called()


@pytest.mark.asyncio
async def test_task_runtime_service_shutdown_stops_workers():
    orchestrator = AgentOrchestrator(MagicMock(), MagicMock())
    worker_a = MagicMock()
    worker_a.stop = AsyncMock(return_value=None)
    worker_b = MagicMock()
    worker_b.stop = AsyncMock(return_value=None)
    orchestrator._task_workers = {"u1": worker_a, "u2": worker_b}

    await orchestrator.shutdown()

    worker_a.stop.assert_awaited_once()
    worker_b.stop.assert_awaited_once()
    assert orchestrator._task_workers == {}
