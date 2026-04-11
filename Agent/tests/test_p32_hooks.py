"""
P32 hook system tests.
Validates PRE/POST_TOOL trigger constants and HookRegistry fire behavior.
"""

import pytest
from core.hooks.triggers import (
    TOOL_PRE_EXECUTE,
    TOOL_POST_EXECUTE,
    TASK_COMPLETE,
    HookTrigger,
)
from core.hooks.registry import HookRegistry
from core.hooks.actions import LogAction, ActionResult


# ── Trigger constants ─────────────────────────────────────────────────────────

def test_tool_pre_execute_constant_exists():
    assert TOOL_PRE_EXECUTE == "TOOL_PRE_EXECUTE"

def test_tool_post_execute_constant_exists():
    assert TOOL_POST_EXECUTE == "TOOL_POST_EXECUTE"


# ── HookRegistry fire behavior ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pre_tool_hook_fires_on_matching_event():
    registry = HookRegistry()
    fired = []

    class CaptureAction:
        async def execute(self, context):
            fired.append(context.get("tool_name"))
            return ActionResult(success=True, action_type="capture")

    trigger = HookTrigger(event_type=TOOL_PRE_EXECUTE)
    registry.register(trigger, CaptureAction())

    await registry.fire(TOOL_PRE_EXECUTE, {"tool_name": "file_read"})

    assert fired == ["file_read"]


@pytest.mark.asyncio
async def test_post_tool_hook_fires_on_matching_event():
    registry = HookRegistry()
    fired = []

    class CaptureAction:
        async def execute(self, context):
            fired.append(context.get("tool_name"))
            return ActionResult(success=True, action_type="capture")

    trigger = HookTrigger(event_type=TOOL_POST_EXECUTE)
    registry.register(trigger, CaptureAction())

    await registry.fire(TOOL_POST_EXECUTE, {"tool_name": "bash", "success": True})

    assert fired == ["bash"]


@pytest.mark.asyncio
async def test_hook_does_not_fire_for_wrong_event():
    registry = HookRegistry()
    fired = []

    class CaptureAction:
        async def execute(self, context):
            fired.append(True)
            return ActionResult(success=True, action_type="capture")

    trigger = HookTrigger(event_type=TOOL_PRE_EXECUTE)
    registry.register(trigger, CaptureAction())

    # Fire a different event — should not trigger
    await registry.fire(TOOL_POST_EXECUTE, {"tool_name": "file_read"})

    assert fired == []


@pytest.mark.asyncio
async def test_hook_with_condition_filter_only_fires_for_match():
    registry = HookRegistry()
    fired = []

    class CaptureAction:
        async def execute(self, context):
            fired.append(context.get("tool_name"))
            return ActionResult(success=True, action_type="capture")

    # Only fire for bash
    trigger = HookTrigger(
        event_type=TOOL_PRE_EXECUTE,
        condition=lambda ctx: ctx.get("tool_name") == "bash",
    )
    registry.register(trigger, CaptureAction())

    await registry.fire(TOOL_PRE_EXECUTE, {"tool_name": "file_read"})
    await registry.fire(TOOL_PRE_EXECUTE, {"tool_name": "bash"})

    assert fired == ["bash"]


@pytest.mark.asyncio
async def test_log_action_fires_on_task_complete():
    registry = HookRegistry()
    log_entries = []

    class CapturingLogger:
        def info(self, msg):
            log_entries.append(msg)

    trigger = HookTrigger(event_type=TASK_COMPLETE)
    registry.register(trigger, LogAction(event_name="task_done", logger=CapturingLogger()))

    result = await registry.fire(TASK_COMPLETE, {"task_id": "t1"})

    assert result["matched"] == 1
    assert result["success_count"] == 1
    assert len(log_entries) == 1


@pytest.mark.asyncio
async def test_multiple_hooks_fire_in_priority_order():
    registry = HookRegistry()
    order = []

    class OrderCapture:
        def __init__(self, label):
            self.label = label
        async def execute(self, context):
            order.append(self.label)
            return ActionResult(success=True, action_type="capture")

    registry.register(HookTrigger(event_type=TOOL_PRE_EXECUTE, priority=1), OrderCapture("low"))
    registry.register(HookTrigger(event_type=TOOL_PRE_EXECUTE, priority=10), OrderCapture("high"))
    registry.register(HookTrigger(event_type=TOOL_PRE_EXECUTE, priority=5), OrderCapture("mid"))

    await registry.fire(TOOL_PRE_EXECUTE, {})

    assert order == ["high", "mid", "low"]


@pytest.mark.asyncio
async def test_empty_registry_fire_returns_zero_matched():
    registry = HookRegistry()
    result = await registry.fire(TOOL_PRE_EXECUTE, {})
    assert result["matched"] == 0
    assert result["executed"] == 0
