import asyncio

import pytest

from core.hooks import (
    AGENT_HANDOFF,
    MESSAGE_RECEIVED,
    SKILL_EXECUTED,
    TASK_COMPLETE,
    TASK_FAILED,
    ActionResult,
    HookAction,
    HookRegistry,
    HookTrigger,
    LogAction,
    NotifyAction,
    SkillAction,
)
from core.skills import SkillResult


class _RecordingAction(HookAction):
    def __init__(self, name, sink, success=True):
        self.name = name
        self.sink = sink
        self.success = success

    async def execute(self, context):
        self.sink.append((self.name, context.get("event_type"), context.get("value")))
        return ActionResult(success=self.success, action_type=self.name, data={"name": self.name})


class _ExplodingAction(HookAction):
    async def execute(self, context):
        raise RuntimeError("boom")


class _AsyncBus:
    def __init__(self):
        self.events = []

    async def publish(self, topic, payload):
        self.events.append((topic, payload))
        return {"ok": True}


class _SyncBus:
    def __init__(self):
        self.events = []

    def publish(self, topic, payload):
        self.events.append((topic, payload))
        return {"ok": True}


class _FakeSkillExecutor:
    def __init__(self, *, succeed=True):
        self.calls = []
        self.succeed = succeed

    async def execute(self, skill_name, params, *, user_role, context):
        self.calls.append((skill_name, params, user_role, context))
        if self.succeed:
            return SkillResult(success=True, data={"skill": skill_name, "params": params})
        return SkillResult(success=False, error="skill_failed")


class _FakeLogger:
    def __init__(self):
        self.entries = []

    def info(self, line):
        self.entries.append(line)


def test_trigger_matches_event_without_condition():
    trigger = HookTrigger(event_type=TASK_COMPLETE)

    assert trigger.matches(TASK_COMPLETE, {"a": 1}) is True
    assert trigger.matches(TASK_FAILED, {"a": 1}) is False


def test_trigger_respects_condition_true_and_false():
    trigger = HookTrigger(event_type=TASK_COMPLETE, condition=lambda ctx: ctx.get("ok") is True)

    assert trigger.matches(TASK_COMPLETE, {"ok": True}) is True
    assert trigger.matches(TASK_COMPLETE, {"ok": False}) is False


def test_trigger_condition_exception_is_treated_as_no_match():
    trigger = HookTrigger(event_type=MESSAGE_RECEIVED, condition=lambda ctx: 1 / 0)

    assert trigger.matches(MESSAGE_RECEIVED, {"msg": "x"}) is False


@pytest.mark.asyncio
async def test_registry_register_and_count_bindings():
    registry = HookRegistry()
    sink = []

    registry.register(HookTrigger(event_type=TASK_COMPLETE), _RecordingAction("a", sink))
    registry.register(HookTrigger(event_type=TASK_FAILED), _RecordingAction("b", sink))

    assert registry.count() == 2


@pytest.mark.asyncio
async def test_registry_fire_executes_matching_action_only():
    registry = HookRegistry()
    sink = []
    registry.register(HookTrigger(event_type=TASK_COMPLETE), _RecordingAction("done", sink))
    registry.register(HookTrigger(event_type=TASK_FAILED), _RecordingAction("failed", sink))

    result = await registry.fire(TASK_COMPLETE, {"value": 5})

    assert result["matched"] == 1
    assert sink == [("done", TASK_COMPLETE, 5)]


@pytest.mark.asyncio
async def test_registry_fire_orders_by_priority_descending():
    registry = HookRegistry()
    sink = []
    registry.register(HookTrigger(event_type=SKILL_EXECUTED, priority=1), _RecordingAction("low", sink))
    registry.register(HookTrigger(event_type=SKILL_EXECUTED, priority=10), _RecordingAction("high", sink))
    registry.register(HookTrigger(event_type=SKILL_EXECUTED, priority=5), _RecordingAction("mid", sink))

    await registry.fire(SKILL_EXECUTED, {"value": 2})

    assert [row[0] for row in sink] == ["high", "mid", "low"]


@pytest.mark.asyncio
async def test_registry_fire_applies_condition_matching():
    registry = HookRegistry()
    sink = []
    registry.register(
        HookTrigger(event_type=AGENT_HANDOFF, condition=lambda ctx: ctx.get("target") == "security"),
        _RecordingAction("match", sink),
    )

    first = await registry.fire(AGENT_HANDOFF, {"target": "coder"})
    second = await registry.fire(AGENT_HANDOFF, {"target": "security"})

    assert first["matched"] == 0
    assert second["matched"] == 1
    assert sink[-1][0] == "match"


@pytest.mark.asyncio
async def test_registry_fire_handles_action_exception_as_failure():
    registry = HookRegistry()
    registry.register(HookTrigger(event_type=TASK_FAILED), _ExplodingAction())

    result = await registry.fire(TASK_FAILED, {"value": 1})

    assert result["matched"] == 1
    assert result["failure_count"] == 1
    assert "action_execution_failed" in str(result["results"][0]["error"])


@pytest.mark.asyncio
async def test_registry_fire_with_no_matches_returns_empty_result():
    registry = HookRegistry()

    result = await registry.fire(TASK_COMPLETE, {"value": 1})

    assert result["matched"] == 0
    assert result["results"] == []


@pytest.mark.asyncio
async def test_notify_action_publishes_with_async_bus():
    bus = _AsyncBus()
    action = NotifyAction(message_bus=bus, topic="hooks.test")

    result = await action.execute({"event_type": TASK_COMPLETE, "value": 3})

    assert result.success is True
    assert bus.events[0][0] == "hooks.test"
    assert bus.events[0][1]["event_type"] == TASK_COMPLETE


@pytest.mark.asyncio
async def test_notify_action_publishes_with_sync_bus():
    bus = _SyncBus()
    action = NotifyAction(message_bus=bus, topic="hooks.sync")

    result = await action.execute({"event_type": TASK_FAILED})

    assert result.success is True
    assert bus.events[0][0] == "hooks.sync"


@pytest.mark.asyncio
async def test_notify_action_returns_failure_when_bus_missing():
    action = NotifyAction(message_bus=None)

    result = await action.execute({"event_type": TASK_COMPLETE})

    assert result.success is False
    assert result.error == "message_bus_unavailable"


@pytest.mark.asyncio
async def test_notify_action_uses_custom_payload_builder():
    bus = _AsyncBus()
    action = NotifyAction(
        message_bus=bus,
        payload_builder=lambda ctx: {"kind": "custom", "value": ctx.get("value")},
    )

    await action.execute({"event_type": TASK_COMPLETE, "value": 9})

    assert bus.events[0][1] == {"kind": "custom", "value": 9}


@pytest.mark.asyncio
async def test_skill_action_executes_skill_successfully():
    fake = _FakeSkillExecutor(succeed=True)
    action = SkillAction(skill_name="web_search", skill_executor=fake)

    result = await action.execute({"event_type": SKILL_EXECUTED, "params": {"query": "maya"}})

    assert result.success is True
    assert fake.calls[0][0] == "web_search"
    assert fake.calls[0][1] == {"query": "maya"}


@pytest.mark.asyncio
async def test_skill_action_uses_params_builder_when_provided():
    fake = _FakeSkillExecutor(succeed=True)
    action = SkillAction(
        skill_name="code_analysis",
        skill_executor=fake,
        params_builder=lambda ctx: {"file_path": ctx.get("path")},
    )

    result = await action.execute({"event_type": AGENT_HANDOFF, "path": "src/a.py"})

    assert result.success is True
    assert fake.calls[0][1] == {"file_path": "src/a.py"}


@pytest.mark.asyncio
async def test_skill_action_propagates_failure_result():
    fake = _FakeSkillExecutor(succeed=False)
    action = SkillAction(skill_name="web_search", skill_executor=fake)

    result = await action.execute({"event_type": SKILL_EXECUTED, "params": {"query": "x"}})

    assert result.success is False
    assert result.error == "skill_failed"


@pytest.mark.asyncio
async def test_log_action_writes_structured_entry_to_logger():
    logger = _FakeLogger()
    action = LogAction(event_name="hook_test", logger=logger)

    result = await action.execute({"event_type": MESSAGE_RECEIVED, "payload": "hello"})

    assert result.success is True
    assert len(logger.entries) == 1
    assert "hook_test" in logger.entries[0]


@pytest.mark.asyncio
async def test_registry_fire_reports_success_and_failure_counts():
    registry = HookRegistry()
    sink = []
    registry.register(HookTrigger(event_type=TASK_COMPLETE, priority=1), _RecordingAction("ok", sink, success=True))
    registry.register(HookTrigger(event_type=TASK_COMPLETE, priority=0), _RecordingAction("bad", sink, success=False))

    result = await registry.fire(TASK_COMPLETE, {"value": 1})

    assert result["executed"] == 2
    assert result["success_count"] == 1
    assert result["failure_count"] == 1


@pytest.mark.asyncio
async def test_registry_clear_removes_bindings():
    registry = HookRegistry()
    sink = []
    registry.register(HookTrigger(event_type=TASK_COMPLETE), _RecordingAction("ok", sink))
    registry.clear()

    result = await registry.fire(TASK_COMPLETE, {"value": 1})

    assert registry.count() == 0
    assert result["matched"] == 0
