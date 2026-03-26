import pytest
import asyncio
import os
import sqlite3
from core.tasks.task_store import SQLiteTaskStore
from core.tasks.task_models import Task, TaskStep, TaskStatus

@pytest.mark.asyncio
async def test_sqlite_taskstore_crud(tmp_path):
    db_path = tmp_path / "test.db"
    # Initialize basic schema 
    # (Since SQLiteTaskStore assumes schema exists or we rely on it? 
    # actually my implementation of SQLiteTaskStore checks connection but NOT schema creation.
    # The migration script strictly ran on dev_maya_one.db.
    # For independent unit test, I should probably apply schema or update SQLiteTaskStore to creating it if missing?
    # The `implementation_plan.md` said: "Ensure TaskStore has an abstract interface and a Supabase AND InMemory/SQLite implementation."
    # The user's earlier SQL migration commands were manual.
    # To make this test self-contained, I should init schema here.
    
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
        CREATE TABLE tasks (
          id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          title TEXT,
          description TEXT,
          status TEXT DEFAULT 'PENDING',
          priority TEXT DEFAULT 'MEDIUM',
          created_at DATETIME,
          updated_at DATETIME,
          current_step_index INTEGER DEFAULT 0,
          progress_notes JSON,
          delegation_depth INTEGER DEFAULT 0,
          delegation_chain JSON,
          result TEXT,
          error TEXT,
          metadata JSON
        );
        CREATE TABLE task_steps (
          id TEXT PRIMARY KEY,
          task_id TEXT NOT NULL,
          seq INTEGER NOT NULL,
          description TEXT,
          tool TEXT,
          parameters JSON,
          status TEXT DEFAULT 'pending',
          result TEXT,
          error TEXT,
          retry_count INTEGER DEFAULT 0,
          worker TEXT DEFAULT 'general',
          created_at DATETIME,
          completed_at DATETIME,
          metadata JSON,
 verification_type TEXT,
 expected_path TEXT,
 expected_selector TEXT,
 expected_url_pattern TEXT,
 success_criteria TEXT,
 step_timeout_seconds INTEGER DEFAULT 300

        );
        """)
    
    db = SQLiteTaskStore(str(db_path))
    
    # Create Task
    task = Task(user_id="user1", title="Test Task", description="Do something")
    step1 = TaskStep(description="Step 1")
    task.steps = [step1]
    
    created = await db.create_task(task)
    assert created is True
    
    # Get Task
    fetched = await db.get_task(task.id)
    assert fetched is not None
    assert fetched.id == task.id
    assert fetched.title == "Test Task"
    assert len(fetched.steps) == 1
    assert fetched.steps[0].description == "Step 1"
    
    # Update Task
    fetched.status = "RUNNING"
    updated = await db.update_task(fetched)
    assert updated is True
    
    fetched_again = await db.get_task(task.id)
    assert fetched_again.status == "RUNNING"

    # List Tasks
    tasks = await db.list_tasks(user_id="user1")
    assert len(tasks) == 1
    assert tasks[0].id == task.id

    # STALE tasks must be excluded from active polling.
    fetched_again.status = TaskStatus.STALE
    await db.update_task(fetched_again)
    active_tasks = await db.get_active_tasks("user1")
    assert active_tasks == []


def test_task_store_indexes_exist(tmp_path):
    db_path = tmp_path / "index_check.db"
    SQLiteTaskStore(str(db_path))

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'index' AND tbl_name = 'tasks'
            """
        ).fetchall()

    index_names = {row[0] for row in rows}
    assert "idx_tasks_created_at" in index_names
    assert "idx_tasks_status" in index_names


def test_sqlite_taskstore_self_heals_legacy_step_columns(tmp_path):
    db_path = tmp_path / "legacy_steps.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE tasks (
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              title TEXT,
              description TEXT,
              status TEXT,
              created_at TEXT,
              metadata TEXT
            );
            CREATE TABLE task_steps (
              id TEXT PRIMARY KEY,
              task_id TEXT NOT NULL,
              seq INTEGER,
              description TEXT,
              tool TEXT,
              worker TEXT,
              status TEXT,
              parameters TEXT,
              result TEXT,
              error TEXT
            );
            """
        )

    SQLiteTaskStore(str(db_path))

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(task_steps)").fetchall()
        }

    assert "verification_type" in columns
    assert "expected_path" in columns
    assert "expected_selector" in columns
    assert "expected_url_pattern" in columns
    assert "success_criteria" in columns
    assert "step_timeout_seconds" in columns
