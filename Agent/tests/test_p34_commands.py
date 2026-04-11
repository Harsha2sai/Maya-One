from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.commands.handlers.agent import handle_agents, handle_kill, handle_spawn
from core.commands.handlers.buddy import handle_buddy, handle_xp
from core.commands.handlers.mode import handle_mode
from core.commands.handlers.system import handle_help, handle_status
from core.commands.registry import CommandRegistry, SlashCommand
from core.permissions.contracts import PermissionMode


def _build_registry() -> CommandRegistry:
    registry = CommandRegistry()
    registry.register(SlashCommand("spawn", "Spawn agent", "/spawn <type> <task>", handle_spawn))
    registry.register(SlashCommand("agents", "List agents", "/agents", handle_agents))
    registry.register(SlashCommand("kill", "Kill agent", "/kill <id>", handle_kill))
    registry.register(SlashCommand("buddy", "Buddy status", "/buddy", handle_buddy))
    registry.register(SlashCommand("xp", "Buddy xp", "/xp", handle_xp))
    registry.register(SlashCommand("mode", "Set mode", "/mode [mode]", handle_mode))
    registry.register(SlashCommand("help", "Show help", "/help", handle_help))
    registry.register(SlashCommand("status", "Show status", "/status", handle_status))
    return registry


@pytest.mark.asyncio
async def test_help_returns_list_of_commands():
    registry = _build_registry()
    out = await registry.dispatch("/help", {"command_registry": registry})
    assert "Available commands:" in out
    assert "/spawn" in out


@pytest.mark.asyncio
async def test_spawn_without_args_returns_usage():
    registry = _build_registry()
    out = await registry.dispatch("/spawn", {})
    assert out.startswith("Usage: /spawn")


@pytest.mark.asyncio
async def test_spawn_calls_subagent_manager_spawn():
    registry = _build_registry()
    mgr = SimpleNamespace(spawn=AsyncMock(return_value=SimpleNamespace(id="agent-1")))

    out = await registry.dispatch(
        "/spawn researcher summarize asyncio gather",
        {"subagent_manager": mgr},
    )

    mgr.spawn.assert_awaited_once()
    kwargs = mgr.spawn.await_args.kwargs
    assert kwargs["agent_type"] == "researcher"
    assert kwargs["wait"] is False
    assert "agent-1" in out


@pytest.mark.asyncio
async def test_agents_with_no_active_returns_empty_message():
    registry = _build_registry()
    out = await registry.dispatch("/agents", {"subagent_manager": SimpleNamespace(active={})})
    assert out == "No active agents."


@pytest.mark.asyncio
async def test_mode_without_args_returns_current():
    registry = _build_registry()

    class Gate:
        @staticmethod
        def get_mode():
            return PermissionMode.DEFAULT

    out = await registry.dispatch("/mode", {"execution_gate": Gate})
    assert "Current mode:" in out


@pytest.mark.asyncio
async def test_mode_plan_calls_set_mode():
    registry = _build_registry()

    class Gate:
        last_mode = None

        @staticmethod
        def get_mode():
            return PermissionMode.DEFAULT

        @classmethod
        def set_mode(cls, mode):
            cls.last_mode = mode

    out = await registry.dispatch("/mode plan", {"execution_gate": Gate})
    assert "Mode set to: plan" in out
    assert Gate.last_mode == PermissionMode.PLAN


@pytest.mark.asyncio
async def test_buddy_returns_render_string():
    registry = _build_registry()
    buddy = SimpleNamespace(status=lambda: "buddy: stage=2 xp=250")
    out = await registry.dispatch("/buddy", {"buddy": buddy})
    assert "stage=2" in out


@pytest.mark.asyncio
async def test_unknown_command_returns_error():
    registry = _build_registry()
    out = await registry.dispatch("/doesnotexist", {})
    assert out.startswith("Unknown command:")


@pytest.mark.asyncio
async def test_non_slash_input_returns_none():
    registry = _build_registry()
    out = await registry.dispatch("hello", {})
    assert out is None


@pytest.mark.asyncio
async def test_status_includes_buddy_mode_and_agent_count():
    registry = _build_registry()
    buddy = SimpleNamespace(status=lambda: "buddy ok")

    class Gate:
        @staticmethod
        def get_mode():
            return PermissionMode.AUTO

    mgr = SimpleNamespace(active={"a1": object(), "a2": object()})
    out = await registry.dispatch(
        "/status",
        {
            "buddy": buddy,
            "execution_gate": Gate,
            "subagent_manager": mgr,
        },
    )
    assert "buddy ok" in out
    assert "Mode:" in out
    assert "Active agents: 2" in out

