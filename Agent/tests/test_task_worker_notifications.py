from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.orchestrator.agent_orchestrator import AgentOrchestrator
from core.tasks.task_models import Task, TaskStatus
from core.tasks.task_worker import TaskWorker


@pytest.mark.asyncio
async def test_worker_plan_failed_emits_event_via_notifier():
    notifier = AsyncMock()
    worker = TaskWorker(user_id="u1", interval=0.0, event_notifier=notifier)
    task = Task(
        user_id="u1",
        title="x",
        steps=[],
        status=TaskStatus.PLAN_FAILED,
        metadata={"trace_id": "trace-1", "session_id": "s1"},
    )

    await worker._process_single_task(task)

    notifier.assert_awaited_once()
    payload = notifier.await_args.args[0]
    assert payload["event_type"] == "plan_failed"
    assert payload["task_id"] == task.id
    assert payload["voice_text"] == "I wasn't able to plan that task."


@pytest.mark.asyncio
async def test_orchestrator_registers_worker_notifier_callback():
    agent = MagicMock()
    agent.smart_llm = None
    orchestrator = AgentOrchestrator(MagicMock(), agent)

    mock_worker = MagicMock()
    mock_worker.start = AsyncMock()
    mock_worker.is_running = False

    with patch("core.tasks.task_worker.TaskWorker", return_value=mock_worker) as worker_cls:
        await orchestrator._ensure_task_worker("u1")

    kwargs = worker_cls.call_args.kwargs
    assert "event_notifier" in kwargs
    assert callable(kwargs["event_notifier"])


@pytest.mark.asyncio
async def test_plan_failed_path_calls_notifier_once():
    agent = MagicMock()
    agent.smart_llm = None
    orchestrator = AgentOrchestrator(MagicMock(), agent)
    orchestrator._handle_task_worker_event = AsyncMock()
    orchestrator.task_store.create_task = AsyncMock(return_value=True)
    orchestrator.task_store.add_log = AsyncMock(return_value=True)

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

    response = await orchestrator._handle_task_request("plan this", "u1")

    assert "couldn't create a safe executable plan" in response.lower()
    orchestrator._handle_task_worker_event.assert_awaited_once()
