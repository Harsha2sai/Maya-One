from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from core.tasks.task_models import Task, TaskStatus
from core.tasks.task_steps import TaskStep, TaskStepStatus
from core.tasks.task_worker import TaskWorker


@pytest.mark.asyncio
async def test_recent_running_task_from_previous_worker_marked_stale_and_skipped():
    notifier = AsyncMock()
    worker = TaskWorker(user_id="u1", interval=0.0, event_notifier=notifier)
    worker.manager.store.update_task = AsyncMock(return_value=True)
    worker.manager.store.add_log = AsyncMock(return_value=True)
    worker.atomic_store.claim_or_renew = AsyncMock()
    worker._execute_next_step = AsyncMock()

    task = Task(
        user_id="u1",
        title="recent running",
        status=TaskStatus.RUNNING,
        steps=[TaskStep(description="s1", status=TaskStepStatus.PENDING)],
        metadata={"claimed_by": "worker:old", "trace_id": "trace-1"},
    )
    task.updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)

    await worker._process_single_task(task)

    assert task.status == TaskStatus.STALE
    worker.atomic_store.claim_or_renew.assert_not_called()
    worker._execute_next_step.assert_not_called()
    notifier.assert_awaited_once()
    assert notifier.await_args.args[0]["event_type"] == "task_stale"


@pytest.mark.asyncio
async def test_old_running_task_can_be_reclaimed_and_processed():
    worker = TaskWorker(user_id="u1", interval=0.0)
    worker.manager.store.update_task = AsyncMock(return_value=True)
    worker.atomic_store.heartbeat = AsyncMock(return_value=True)
    worker._execute_next_step = AsyncMock()
    worker._is_task_stuck = AsyncMock(return_value=False)

    task = Task(
        user_id="u1",
        title="old running",
        status=TaskStatus.RUNNING,
        steps=[TaskStep(description="s1", status=TaskStepStatus.PENDING)],
        metadata={"claimed_by": "worker:old", "trace_id": "trace-1"},
    )
    task.updated_at = datetime.now(timezone.utc) - timedelta(seconds=180)
    worker.atomic_store.claim_or_renew = AsyncMock(return_value=task)

    await worker._process_single_task(task)

    worker.atomic_store.claim_or_renew.assert_awaited_once()
    worker._execute_next_step.assert_awaited_once()
