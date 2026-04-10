from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core.agents.coding.ralph_mode import RalphExecutor, RalphState
from core.agents.subagent.types import SubAgentInstance, SubAgentStatus


def _make_instance(result: str = "done", status: SubAgentStatus = SubAgentStatus.COMPLETED):
    return SubAgentInstance(
        id="agent-coder",
        agent_type="coder",
        task="task",
        status=status,
        result=result,
    )


@pytest.mark.asyncio
async def test_run_completes_when_terminal_signal(tmp_path: Path):
    manager = AsyncMock()
    manager.spawn = AsyncMock(return_value=_make_instance("done - complete"))
    executor = RalphExecutor(manager, store_path=tmp_path)

    result = await executor.run("build a thing", max_iterations=2)

    assert result.succeeded is True
    state = await executor.get_state("build a thing")
    assert state is not None
    assert state.status == "completed"


@pytest.mark.asyncio
async def test_run_fails_after_error_threshold(tmp_path: Path):
    manager = AsyncMock()
    manager.spawn = AsyncMock(side_effect=RuntimeError("boom"))
    executor = RalphExecutor(manager, store_path=tmp_path)

    async def _no_sleep(_duration):
        return None

    executor._sleep = _no_sleep

    result = await executor.run("fail task", error_threshold=2, max_iterations=5)

    assert result.succeeded is False
    assert result.state.status == "failed"
    assert len(result.state.errors) >= 2


@pytest.mark.asyncio
async def test_get_state_returns_none_for_unknown_task(tmp_path: Path):
    manager = AsyncMock()
    executor = RalphExecutor(manager, store_path=tmp_path)

    state = await executor.get_state("unknown")

    assert state is None


@pytest.mark.asyncio
async def test_state_persists_and_resumes(tmp_path: Path):
    manager = AsyncMock()
    manager.spawn = AsyncMock(return_value=_make_instance("implemented", SubAgentStatus.COMPLETED))
    executor = RalphExecutor(manager, store_path=tmp_path)

    running_state = RalphState(
        task="resume task",
        task_hash=hash("resume task"),
        status="running",
        iteration=1,
        last_output="partial",
    )
    await executor._persist(running_state)

    resumed = await executor.run("resume task", max_iterations=2)

    assert resumed.state.iteration >= 1
    assert resumed.state.status in {"completed", "failed"}


@pytest.mark.asyncio
async def test_backoff_capped(tmp_path: Path):
    manager = AsyncMock()
    manager.spawn = AsyncMock(side_effect=RuntimeError("boom"))
    executor = RalphExecutor(manager, store_path=tmp_path)

    durations = []

    async def _record_sleep(duration):
        durations.append(duration)
        return None

    executor._sleep = _record_sleep

    result = await executor.run("backoff", error_threshold=1, max_iterations=1)

    assert result.state.status == "failed"
    assert all(d <= 30 for d in durations)
