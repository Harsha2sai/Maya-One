
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

from core.tasks.atomic_task_state import AtomicTaskStore, TaskStateMachine
from core.tasks.task_models import Task, TaskStatus
from core.tasks.task_steps import TaskStep, TaskStepStatus
from core.tasks.task_store import TaskStore


@pytest.mark.phase4
class TestTaskStateMachine:
    def test_valid_task_transitions(self):
        assert TaskStateMachine.can_transition(TaskStatus.PENDING, TaskStatus.RUNNING) is True
        assert TaskStateMachine.can_transition(TaskStatus.PENDING, TaskStatus.CANCELLED) is True
        assert TaskStateMachine.can_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED) is True
        assert TaskStateMachine.can_transition(TaskStatus.RUNNING, TaskStatus.FAILED) is True
        assert TaskStateMachine.can_transition(TaskStatus.RUNNING, TaskStatus.STALE) is True

    def test_invalid_task_transitions(self):
        assert TaskStateMachine.can_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING) is False
        assert TaskStateMachine.can_transition(TaskStatus.FAILED, TaskStatus.COMPLETED) is False
        assert TaskStateMachine.can_transition(TaskStatus.PENDING, TaskStatus.COMPLETED) is False
        assert TaskStateMachine.can_transition(TaskStatus.STALE, TaskStatus.RUNNING) is False

    def test_valid_step_transitions(self):
        assert TaskStateMachine.can_step_transition(TaskStepStatus.PENDING, TaskStepStatus.RUNNING) is True
        assert TaskStateMachine.can_step_transition(TaskStepStatus.RUNNING, TaskStepStatus.DONE) is True
        assert TaskStateMachine.can_step_transition(TaskStepStatus.RUNNING, TaskStepStatus.FAILED) is True

    def test_invalid_step_transitions(self):
        assert TaskStateMachine.can_step_transition(TaskStepStatus.DONE, TaskStepStatus.RUNNING) is False
        assert TaskStateMachine.can_step_transition(TaskStepStatus.FAILED, TaskStepStatus.DONE) is False
        assert TaskStateMachine.can_step_transition(TaskStepStatus.PENDING, TaskStepStatus.DONE) is False


@pytest.fixture
def mock_store():
    store = MagicMock(spec=TaskStore)
    return store


@pytest.mark.asyncio
async def test_claim_task_success(mock_store):
    task = Task(
        id="test-1",
        user_id="user1",
        title="Test Task",
        status=TaskStatus.PENDING,
        steps=[TaskStep(description="Step 1")]
    )
    mock_store.get_task = AsyncMock(return_value=task)
    mock_store.update_task = AsyncMock(return_value=True)

    atomic = AtomicTaskStore(mock_store)
    result = await atomic.claim_task("test-1", "worker-1")

    assert result is not None
    assert result.status == TaskStatus.RUNNING
    assert result.metadata["claimed_by"] == "worker-1"
    mock_store.update_task.assert_called_once()


@pytest.mark.asyncio
async def test_claim_task_wrong_state(mock_store):
    task = Task(
        id="test-1",
        user_id="user1",
        title="Test Task",
        status=TaskStatus.RUNNING,
        steps=[TaskStep(description="Step 1")]
    )
    mock_store.get_task = AsyncMock(return_value=task)

    atomic = AtomicTaskStore(mock_store)
    result = await atomic.claim_task("test-1", "worker-1")

    assert result is None


@pytest.mark.asyncio
async def test_update_step_status_idempotency(mock_store):
    step = TaskStep(id="s1", description="Step 1", status=TaskStepStatus.RUNNING)
    task = Task(
        id="test-1",
        user_id="user1",
        title="Test Task",
        status=TaskStatus.RUNNING,
        steps=[step],
        metadata={}
    )
    mock_store.get_task = AsyncMock(return_value=task)
    mock_store.update_task = AsyncMock(return_value=True)

    atomic = AtomicTaskStore(mock_store)
    
    idempotency_key = "unique-key-123"
    
    success, result = await atomic.update_step_status(
        "test-1", 0, TaskStepStatus.DONE, 
        result="Success", 
        idempotency_key=idempotency_key
    )
    
    assert success is True
    assert result.steps[0].status == TaskStepStatus.DONE
    assert result.steps[0].metadata["last_idempotency_key"] == idempotency_key

    step.status = TaskStepStatus.DONE
    success2, _ = await atomic.update_step_status(
        "test-1", 0, TaskStepStatus.DONE,
        idempotency_key=idempotency_key
    )
    
    assert success2 is True


@pytest.mark.asyncio
async def test_update_step_invalid_transition(mock_store):
    step = TaskStep(id="s1", description="Step 1", status=TaskStepStatus.DONE)
    task = Task(
        id="test-1",
        user_id="user1",
        title="Test Task",
        status=TaskStatus.RUNNING,
        steps=[step]
    )
    mock_store.get_task = AsyncMock(return_value=task)

    atomic = AtomicTaskStore(mock_store)
    success, _ = await atomic.update_step_status("test-1", 0, TaskStepStatus.RUNNING)
    
    assert success is False


@pytest.mark.asyncio
async def test_heartbeat(mock_store):
    task = Task(
        id="test-1",
        user_id="user1",
        title="Test Task",
        status=TaskStatus.RUNNING,
        metadata={"claimed_by": "worker-1"}
    )
    mock_store.get_task = AsyncMock(return_value=task)
    mock_store.update_task = AsyncMock(return_value=True)

    atomic = AtomicTaskStore(mock_store)
    result = await atomic.heartbeat("test-1", "worker-1")
    
    assert result is True
    assert "last_heartbeat" in task.metadata


@pytest.mark.asyncio
async def test_heartbeat_wrong_worker(mock_store):
    task = Task(
        id="test-1",
        user_id="user1",
        title="Test Task",
        status=TaskStatus.RUNNING,
        metadata={"claimed_by": "worker-1"}
    )
    mock_store.get_task = AsyncMock(return_value=task)

    atomic = AtomicTaskStore(mock_store)
    result = await atomic.heartbeat("test-1", "worker-2")
    
    assert result is False
