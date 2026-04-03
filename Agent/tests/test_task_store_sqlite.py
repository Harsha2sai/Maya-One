import sqlite3

import pytest

from core.tasks.atomic_task_state import AtomicTaskStore
from core.tasks.task_models import Task, TaskStatus
from core.tasks.task_steps import TaskStep, TaskStepStatus
from core.tasks.task_store import SQLiteTaskStore


def _make_store(tmp_path):
    return SQLiteTaskStore(str(tmp_path / "tasks.db"))


def _make_task():
    return Task(
        user_id="task-user",
        title="Task Title",
        description="Task Description",
        steps=[TaskStep(description="First step")],
    )


def test_sqlite_task_store_enables_wal_mode(tmp_path):
    db_path = tmp_path / "tasks.db"
    store = SQLiteTaskStore(str(db_path))

    with sqlite3.connect(db_path) as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    with store._get_conn() as conn:
        synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]

    assert journal_mode == "wal"
    assert synchronous == 1


@pytest.mark.asyncio
async def test_atomic_step_status_update_is_idempotent_for_duplicate_key(tmp_path):
    store = _make_store(tmp_path)
    task = _make_task()
    assert await store.create_task(task) is True

    atomic_store = AtomicTaskStore(store)
    transitioned, updated_task = await atomic_store.update_step_status(
        task.id,
        0,
        TaskStepStatus.RUNNING,
        idempotency_key="task-1:0:0",
    )

    assert transitioned is True
    assert updated_task is not None
    assert updated_task.steps[0].status == TaskStepStatus.RUNNING
    assert updated_task.steps[0].metadata["last_idempotency_key"] == "task-1:0:0"

    transitioned_again, duplicate_task = await atomic_store.update_step_status(
        task.id,
        0,
        TaskStepStatus.RUNNING,
        idempotency_key="task-1:0:0",
    )

    assert transitioned_again is True
    assert duplicate_task is not None
    assert duplicate_task.steps[0].status == TaskStepStatus.RUNNING
    assert duplicate_task.steps[0].metadata["last_idempotency_key"] == "task-1:0:0"


@pytest.mark.asyncio
async def test_claim_or_renew_does_not_reclaim_fresh_running_task(tmp_path):
    store = _make_store(tmp_path)
    task = _make_task()
    assert await store.create_task(task) is True

    atomic_store = AtomicTaskStore(store)
    claimed = await atomic_store.claim_or_renew(task.id, "worker-a")
    assert claimed is not None
    assert claimed.status == TaskStatus.RUNNING
    assert claimed.metadata["claimed_by"] == "worker-a"

    stolen = await atomic_store.claim_or_renew(task.id, "worker-b")
    assert stolen is None

    persisted = await store.get_task(task.id)
    assert persisted is not None
    assert persisted.status == TaskStatus.RUNNING
    assert persisted.metadata["claimed_by"] == "worker-a"


@pytest.mark.asyncio
async def test_get_active_tasks_coerces_non_string_user_id(tmp_path):
    store = _make_store(tmp_path)
    task = _make_task()
    assert await store.create_task(task) is True

    class _UserLike:
        def __str__(self) -> str:
            return "task-user"

    tasks = await store.get_active_tasks(_UserLike())
    assert len(tasks) == 1
    assert tasks[0].id == task.id
