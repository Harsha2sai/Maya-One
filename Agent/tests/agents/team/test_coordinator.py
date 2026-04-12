from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from core.agents.team.coordinator import TeamCoordinator
from core.agents.team.types import TeamMode
from core.agents.subagent.types import SubAgentInstance, SubAgentStatus


@dataclass
class _DummyHub:
    async def send(self, *_args, **_kwargs):
        return None


def _make_instance(agent_type: str, result: str = "ok") -> SubAgentInstance:
    return SubAgentInstance(
        id=f"agent-{agent_type}",
        agent_type=agent_type,
        task="task",
        status=SubAgentStatus.COMPLETED,
        result=result,
    )


@pytest.mark.asyncio
async def test_parallel_team_returns_instances():
    manager = AsyncMock()
    manager.spawn = AsyncMock(side_effect=[_make_instance("coder"), _make_instance("reviewer")])
    coordinator = TeamCoordinator(manager, _DummyHub())

    result = await coordinator.create_team("do", ["coder", "reviewer"], mode="parallel")

    assert result.mode == TeamMode.PARALLEL
    assert len(result.instances) == 2
    assert result.succeeded is True


@pytest.mark.asyncio
async def test_sequential_team_feeds_output():
    manager = AsyncMock()
    manager.spawn = AsyncMock(side_effect=[
        _make_instance("coder", "first output"),
        _make_instance("reviewer", "final output"),
    ])
    coordinator = TeamCoordinator(manager, _DummyHub())

    result = await coordinator.create_team("base", ["coder", "reviewer"], mode="sequential")

    assert result.mode == TeamMode.SEQUENTIAL
    assert result.final_output == "final output"
    assert manager.spawn.await_count == 2
    _, second_kwargs = manager.spawn.await_args_list[1]
    assert "Previous agent" in second_kwargs["task"]
    assert "first output" in second_kwargs["task"]


@pytest.mark.asyncio
async def test_review_team_approves_early():
    manager = AsyncMock()
    manager.spawn = AsyncMock(side_effect=[
        _make_instance("coder", "code"),
        _make_instance("reviewer", "LGTM looks good"),
    ])
    coordinator = TeamCoordinator(manager, _DummyHub())

    result = await coordinator.create_team("task", ["coder", "reviewer"], mode="review")

    assert result.mode == TeamMode.REVIEW
    assert result.approved is True
    assert len(result.iterations) == 1


@pytest.mark.asyncio
async def test_review_team_runs_max_iterations_when_no_approval():
    manager = AsyncMock()
    manager.spawn = AsyncMock(side_effect=[
        _make_instance("coder", "code1"),
        _make_instance("reviewer", "needs work"),
        _make_instance("coder", "code2"),
        _make_instance("reviewer", "still not"),
        _make_instance("coder", "code3"),
        _make_instance("reviewer", "needs more work"),
    ])
    coordinator = TeamCoordinator(manager, _DummyHub())

    result = await coordinator.create_team("task", ["coder", "reviewer"], mode="review")

    assert result.mode == TeamMode.REVIEW
    assert len(result.iterations) == 3
    assert result.approved is False


@pytest.mark.asyncio
async def test_invalid_mode_raises_value_error():
    manager = AsyncMock()
    coordinator = TeamCoordinator(manager, _DummyHub())

    with pytest.raises(ValueError):
        await coordinator.create_team("task", ["coder"], mode="invalid")
