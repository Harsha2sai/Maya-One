from datetime import datetime, timezone

import pytest

from core.tasks.task_models import Task
from core.tasks.task_persistence import TaskPersistence


class _InMemoryStore:
    def __init__(self, task: Task):
        self.task = task

    async def get_task(self, task_id: str):
        return self.task if self.task.id == task_id else None

    async def update_task(self, task: Task):
        self.task = task
        return True


@pytest.mark.asyncio
async def test_task_persistence_checkpoint_and_resume_markers():
    task = Task(user_id="u1", title="T", description="D")
    store = _InMemoryStore(task)
    persistence = TaskPersistence(store=store)

    checkpoint_id = await persistence.save_checkpoint(
        task_id=task.id,
        step_id="s1",
        payload={"ok": True},
    )
    assert checkpoint_id.startswith("chk_")
    assert store.task.metadata["last_checkpoint_id"] == checkpoint_id

    resumed = await persistence.mark_resumed(task.id, "worker-1")
    assert resumed is True
    assert store.task.metadata["resumed_by"] == "worker-1"

    terminal = await persistence.mark_terminal(task.id, "FAILED", "poisoned")
    assert terminal is True
    assert str(store.task.metadata.get("terminal_reason")) == "poisoned"

