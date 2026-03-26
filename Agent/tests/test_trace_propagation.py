import json
import logging
import sqlite3
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.observability.trace_context import (
    clear_trace_context,
    current_trace_id,
    enable_trace_logging,
    get_trace_context,
    set_trace_context,
    start_trace,
)
from core.orchestrator.agent_orchestrator import AgentOrchestrator
from core.tasks.planning_engine import PlanningEngine
from core.tasks.task_models import Task
from core.tasks.task_steps import TaskStep
from core.tasks.task_store import SQLiteTaskStore


def test_start_trace_assigns_uuid_when_missing():
    clear_trace_context()
    trace_ctx = start_trace(session_id="lifecycle:worker", user_id="system")

    assert "trace_id" in trace_ctx
    assert uuid.UUID(trace_ctx["trace_id"])


def test_enable_trace_logging_injects_trace_fields_on_records():
    clear_trace_context()
    start_trace(trace_id="trace-log-abc", session_id="s1", user_id="u1")
    enable_trace_logging()

    root_logger = logging.getLogger()
    record = logging.LogRecord(
        name="trace_test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    for filt in root_logger.filters:
        filt.filter(record)

    assert record.trace_id == "trace-log-abc"
    assert record.session_id == "s1"
    assert record.user_id == "u1"


@pytest.mark.asyncio
async def test_sqlite_taskstore_create_includes_trace_id(tmp_path: Path):
    clear_trace_context()
    start_trace(trace_id="trace-db-create", session_id="console_session", user_id="u1")
    db_path = tmp_path / "trace_create.db"
    store = SQLiteTaskStore(str(db_path))

    task = Task(user_id="u1", title="Trace task", description="desc", steps=[])
    ok = await store.create_task(task)

    assert ok is True
    assert task.metadata["trace_id"] == "trace-db-create"

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT metadata FROM tasks WHERE id = ?", (task.id,)).fetchone()
    assert row is not None
    metadata = json.loads(row[0])
    assert metadata["trace_id"] == "trace-db-create"


@pytest.mark.asyncio
async def test_sqlite_taskstore_add_log_prefixes_trace_id(caplog, tmp_path: Path):
    clear_trace_context()
    set_trace_context(trace_id="trace-log-write", session_id="s2", user_id="u2")
    store = SQLiteTaskStore(str(tmp_path / "trace_log.db"))

    with caplog.at_level(logging.INFO, logger="core.tasks.task_store"):
        await store.add_log("task-1", "Task created")

    assert "[trace_id=trace-log-write] Task created" in caplog.text


@pytest.mark.asyncio
async def test_orchestrator_propagates_trace_id_to_taskstore():
    clear_trace_context()
    start_trace(trace_id="trace-orch-1", session_id="console_session", user_id="user-1")

    agent = MagicMock()
    agent.smart_llm = None
    orchestrator = AgentOrchestrator(MagicMock(), agent)

    orchestrator._retrieve_memory_context_async = AsyncMock(return_value=None)
    orchestrator._ensure_task_worker = AsyncMock(return_value=None)

    orchestrator.planning_engine.generate_plan_result = AsyncMock(
        return_value=SimpleNamespace(
            steps=[TaskStep(description="Step 1", worker="general")],
            plan_failed=False,
            error_payload=None,
        )
    )

    orchestrator.task_store.create_task = AsyncMock(return_value=True)
    orchestrator.task_store.add_log = AsyncMock(return_value=True)

    await orchestrator._handle_task_request("Create report", user_id="user-1")

    created_task = orchestrator.task_store.create_task.await_args.args[0]
    assert created_task.metadata["trace_id"] == "trace-orch-1"


@pytest.mark.asyncio
async def test_planning_engine_preserves_existing_trace_id():
    clear_trace_context()
    start_trace(trace_id="trace-planner-1", session_id="planner-session", user_id="user-x")

    engine = PlanningEngine(smart_llm=MagicMock())
    engine._run_planner_prompt = AsyncMock(
        return_value=(
            json.dumps(
                {
                    "steps": [
                        {
                            "description": "Do it",
                            "worker": "general",
                        }
                    ]
                }
            ),
            [],
        )
    )

    result = await engine.generate_plan_result("Do it")

    assert result.plan_failed is False
    assert current_trace_id() == "trace-planner-1"
    assert get_trace_context()["trace_id"] == "trace-planner-1"
