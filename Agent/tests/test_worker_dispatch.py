
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from core.tasks.workers.registry import WorkerRegistry
from core.tasks.task_steps import WorkerType, TaskStep, TaskStepStatus
from core.tasks.task_models import Task, TaskStatus

@pytest.fixture
def mock_store():
    return MagicMock()

def test_registry_get_worker(mock_store):
    registry = WorkerRegistry("user1", mock_store)
    
    general = registry.get_worker(WorkerType.GENERAL)
    assert general.worker_type == WorkerType.GENERAL
    
    research = registry.get_worker(WorkerType.RESEARCH)
    assert research.worker_type == WorkerType.RESEARCH

@pytest.mark.asyncio
async def test_worker_execute_tool(mock_store):
    registry = WorkerRegistry("user1", mock_store)
    worker = registry.get_worker(WorkerType.GENERAL)
    
    # Mock router
    with patch("core.tasks.workers.base.get_router") as mock_get_router:
        mock_router = mock_get_router.return_value
        mock_router.tool_executor = AsyncMock(return_value="Tool Output")
        
        # Inject mock router into worker (since __init__ called get_router already)
        worker.router = mock_router
        
        task = Task(
            id="t1",
            user_id="user1",
            title="Task",
            description="Desc",
            steps=[],
            status=TaskStatus.RUNNING,
        )
        step = TaskStep(
            id="s1",
            description="Run tool",
            tool="test_tool",
            parameters={"a": 1},
            worker=WorkerType.GENERAL,
        )
        
        # Mock allowed tools
        with patch("core.tasks.workers.tool_registry.WorkerToolRegistry.is_tool_allowed", return_value=True):
             # Mock update
             worker._update_step_state = AsyncMock()
             worker.store.add_log = AsyncMock()

             success = await worker.execute_step(task, step)
             
             assert success is True
             assert step.status == TaskStepStatus.DONE
             assert step.result == "Tool Output"
             mock_router.tool_executor.assert_called_once()

@pytest.mark.asyncio
async def test_worker_execute_reasoning(mock_store):
    registry = WorkerRegistry("user1", mock_store)
    worker = registry.get_worker(WorkerType.GENERAL)

    # Mock SmartLLM stream used by RoleLLM in BaseWorker._execute_reasoning
    async def mock_stream(*args, **kwargs):
        yield MagicMock(choices=[MagicMock(delta=MagicMock(content="Reasoning result"))])

    worker.smart_llm = MagicMock()
    worker.smart_llm.chat = MagicMock(return_value=mock_stream())

    task = Task(
        id="t1",
        user_id="user1",
        title="Task",
        description="Desc",
        steps=[],
        status=TaskStatus.RUNNING,
    )
    step = TaskStep(id="s1", description="Think", worker=WorkerType.GENERAL)  # No tool

    worker._update_step_state = AsyncMock()
    worker.store.add_log = AsyncMock()

    success = await worker.execute_step(task, step)

    assert success is True
    assert step.result == "Reasoning result"
