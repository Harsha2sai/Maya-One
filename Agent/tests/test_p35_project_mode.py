from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.commands.handlers.project import handle_project
from core.project.orchestrator import ProjectModeOrchestrator
from core.project.models import ProjectPhase


def _build_orchestrator() -> tuple[ProjectModeOrchestrator, SimpleNamespace, SimpleNamespace]:
    async def _spawn(agent_type: str, task: str, wait: bool = True):
        del wait
        if agent_type == "architect" and task.startswith("Generate a concise PRD"):
            return SimpleNamespace(result="PRD body for project")
        if agent_type == "architect" and task.startswith("Break down this PRD"):
            return SimpleNamespace(result="Implement parser\nWrite tests\nDocument API\nReview outputs")
        if agent_type == "coder":
            return SimpleNamespace(result=f"done: {task}")
        if agent_type == "reviewer":
            return SimpleNamespace(result="Review summary: quality acceptable")
        return SimpleNamespace(result="")

    manager = SimpleNamespace(spawn=AsyncMock(side_effect=_spawn))
    buddy = SimpleNamespace(
        on_task_complete=AsyncMock(return_value="ok"),
        on_team_coordinated=AsyncMock(return_value="ok"),
    )
    orchestrator = ProjectModeOrchestrator(manager, buddy, command_registry=SimpleNamespace())
    return orchestrator, manager, buddy


@pytest.mark.asyncio
async def test_start_returns_requirements_prompt():
    pm, _, _ = _build_orchestrator()
    out = await pm.start("Alpha")
    assert "Project 'Alpha' started." in out
    assert "requirements" in out


@pytest.mark.asyncio
async def test_start_twice_returns_in_progress_message():
    pm, _, _ = _build_orchestrator()
    await pm.start("Alpha")
    out = await pm.start("Beta")
    assert "already in progress" in out


@pytest.mark.asyncio
async def test_add_requirement_increments_count():
    pm, _, _ = _build_orchestrator()
    await pm.start("Alpha")
    out = await pm.add_requirement("Need oauth")
    assert "Requirement 1 recorded" in out


@pytest.mark.asyncio
async def test_advance_without_requirements_returns_error():
    pm, _, _ = _build_orchestrator()
    await pm.start("Alpha")
    out = await pm.advance()
    assert out == "No requirements recorded yet."


@pytest.mark.asyncio
async def test_advance_requirements_to_prd_calls_architect_spawn():
    pm, manager, buddy = _build_orchestrator()
    await pm.start("Alpha")
    await pm.add_requirement("Need oauth")
    out = await pm.advance()
    assert "PRD generated" in out
    first = manager.spawn.await_args_list[0]
    assert first.kwargs["agent_type"] == "architect"
    buddy.on_task_complete.assert_awaited()


@pytest.mark.asyncio
async def test_advance_prd_to_planning_calls_architect_spawn():
    pm, manager, _ = _build_orchestrator()
    await pm.start("Alpha")
    await pm.add_requirement("Need oauth")
    await pm.advance()  # generate PRD
    out = await pm.advance()  # generate plan
    assert "Plan generated" in out
    second = manager.spawn.await_args_list[1]
    assert second.kwargs["agent_type"] == "architect"


@pytest.mark.asyncio
async def test_advance_planning_to_execution_calls_coder_spawn():
    pm, manager, buddy = _build_orchestrator()
    await pm.start("Alpha")
    await pm.add_requirement("Need oauth")
    await pm.advance()
    await pm.advance()
    out = await pm.advance()
    assert "Execution complete" in out
    coder_calls = [c for c in manager.spawn.await_args_list if c.kwargs["agent_type"] == "coder"]
    assert len(coder_calls) == 3
    assert buddy.on_task_complete.await_count >= 4


@pytest.mark.asyncio
async def test_advance_execution_to_review_calls_reviewer_spawn():
    pm, manager, buddy = _build_orchestrator()
    await pm.start("Alpha")
    await pm.add_requirement("Need oauth")
    await pm.advance()
    await pm.advance()
    await pm.advance()
    out = await pm.advance()
    assert "Review complete" in out
    reviewer_calls = [c for c in manager.spawn.await_args_list if c.kwargs["agent_type"] == "reviewer"]
    assert len(reviewer_calls) == 1
    buddy.on_team_coordinated.assert_awaited_once()


@pytest.mark.asyncio
async def test_advance_review_to_complete_clears_active_project():
    pm, _, _ = _build_orchestrator()
    await pm.start("Alpha")
    await pm.add_requirement("Need oauth")
    await pm.advance()
    await pm.advance()
    await pm.advance()
    await pm.advance()
    out = await pm.advance()
    assert out == "Project 'Alpha' complete."
    assert pm.is_active() is False


@pytest.mark.asyncio
async def test_status_with_no_project_returns_no_project_message():
    pm, _, _ = _build_orchestrator()
    out = await pm.status()
    assert out == "No active project."


@pytest.mark.asyncio
async def test_cancel_clears_active_project():
    pm, _, _ = _build_orchestrator()
    await pm.start("Alpha")
    out = await pm.cancel()
    assert out == "Project 'Alpha' cancelled."
    assert pm.current_phase() is None


@pytest.mark.asyncio
async def test_project_slash_command_routes_subcommands_correctly():
    pm = SimpleNamespace(
        start=AsyncMock(return_value="started"),
        status=AsyncMock(return_value="status"),
        cancel=AsyncMock(return_value="cancelled"),
        advance=AsyncMock(return_value="advanced"),
        add_requirement=AsyncMock(return_value="req ok"),
    )
    context = {"project_mode": pm}

    assert await handle_project("start Demo", context) == "started"
    assert await handle_project("status", context) == "status"
    assert await handle_project("req Need oauth", context) == "req ok"
    assert await handle_project("next", context) == "advanced"
    assert await handle_project("cancel", context) == "cancelled"
    pm.start.assert_awaited_once_with("Demo")
    pm.status.assert_awaited_once()
    pm.add_requirement.assert_awaited_once_with("Need oauth")
    pm.advance.assert_awaited_once()
    pm.cancel.assert_awaited_once()

