import sqlite3

import pytest

from core.tasks.task_persistence import TaskPersistenceManager


def _bootstrap_tasks_table(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                status TEXT,
                error TEXT,
                updated_at TEXT,
                persistent INTEGER DEFAULT 0,
                cron_expression TEXT,
                recovery_checkpoint TEXT,
                background_mode INTEGER DEFAULT 0
            );
            """
        )


@pytest.mark.asyncio
async def test_save_and_load_checkpoint_round_trip(tmp_path):
    db_path = tmp_path / "tasks.db"
    _bootstrap_tasks_table(str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO tasks (id, user_id, status, persistent, background_mode) VALUES (?, ?, ?, ?, ?)",
            ("task-1", "user-1", "RUNNING", 1, 0),
        )

    manager = TaskPersistenceManager(str(db_path))
    payload = {"event": "subagent_recovery_checkpoint", "state": {"step": "compile"}}

    checkpoint_id = await manager.save_checkpoint("task-1", "step-1", payload)
    loaded = await manager.load_checkpoint("step-1")

    assert checkpoint_id.startswith("chk_")
    assert loaded == payload


@pytest.mark.asyncio
async def test_mark_terminal_updates_task_status(tmp_path):
    db_path = tmp_path / "tasks.db"
    _bootstrap_tasks_table(str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO tasks (id, user_id, status, persistent, background_mode) VALUES (?, ?, ?, ?, ?)",
            ("task-2", "user-1", "RUNNING", 1, 1),
        )

    manager = TaskPersistenceManager(str(db_path))
    ok = await manager.mark_terminal("task-2", "FAILED", "boom")

    assert ok is True
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT status, error FROM tasks WHERE id = ?", ("task-2",)).fetchone()
    assert row == ("FAILED", "boom")


@pytest.mark.asyncio
async def test_recover_background_tasks_filters_non_terminal_rows(tmp_path):
    db_path = tmp_path / "tasks.db"
    _bootstrap_tasks_table(str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO tasks (id, user_id, status, persistent, background_mode, recovery_checkpoint) VALUES (?, ?, ?, ?, ?, ?)",
            ("task-running", "user-1", "RUNNING", 1, 1, '{"event": "checkpoint"}'),
        )
        conn.execute(
            "INSERT INTO tasks (id, user_id, status, persistent, background_mode, recovery_checkpoint) VALUES (?, ?, ?, ?, ?, ?)",
            ("task-done", "user-1", "COMPLETED", 1, 1, '{"event": "checkpoint"}'),
        )

    manager = TaskPersistenceManager(str(db_path))
    recovered = await manager.recover_background_tasks(user_id="user-1")

    assert len(recovered) == 1
    assert recovered[0]["task_id"] == "task-running"
    assert recovered[0]["recovery_checkpoint"]["event"] == "checkpoint"
