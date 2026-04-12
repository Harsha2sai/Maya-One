import asyncio

import pytest

from core.agents.subagent import SubAgentManager
from core.messaging import MayaMsgHub


class _AgentParticipant:
    def __init__(self, name: str):
        self.name = name

    async def reply(self, message):
        return message

    async def observe(self, message):
        return None


def _patch_fast_sleep(monkeypatch):
    real_sleep = asyncio.sleep

    async def _fast_sleep(seconds):
        if seconds >= 300:
            await real_sleep(0)
            return
        await real_sleep(seconds)

    monkeypatch.setattr("core.agents.subagent.manager.asyncio.sleep", _fast_sleep)


@pytest.mark.asyncio
async def test_spawn_background_emits_progress_messages(monkeypatch):
    _patch_fast_sleep(monkeypatch)

    manager = SubAgentManager(msg_hub=MayaMsgHub())
    instance = await manager.spawn(
        agent_type="researcher",
        task="summarize event loop",
        wait=False,
    )

    messages = [msg async for msg in manager.subscribe_to_updates(instance.id, timeout=2.0)]
    contents = [m.content for m in messages]

    assert any("agent_started" in c for c in contents)
    assert any("agent_completed" in c for c in contents)


@pytest.mark.asyncio
async def test_subscribe_exits_when_agent_completes(monkeypatch):
    _patch_fast_sleep(monkeypatch)

    manager = SubAgentManager(msg_hub=MayaMsgHub())
    instance = await manager.spawn(
        agent_type="coder",
        task="write one helper",
        wait=False,
    )

    loop = asyncio.get_running_loop()
    started = loop.time()
    _ = [msg async for msg in manager.subscribe_to_updates(instance.id, timeout=2.0)]
    elapsed = loop.time() - started

    assert elapsed < 2.0


@pytest.mark.asyncio
async def test_hub_auto_opens_on_first_broadcast():
    hub = MayaMsgHub()
    hub.register("listener", _AgentParticipant("listener"))
    assert not hub.is_active

    await hub.broadcast(sender="agent-1", content="agent_started", role="system")
    assert hub.is_active


@pytest.mark.asyncio
async def test_broadcast_start_and_completion(monkeypatch):
    _patch_fast_sleep(monkeypatch)

    manager = SubAgentManager(msg_hub=MayaMsgHub())
    instance = await manager.spawn(
        agent_type="reviewer",
        task="review this patch",
        wait=False,
    )

    messages = [msg async for msg in manager.subscribe_to_updates(instance.id, timeout=2.0)]
    contents = [m.content for m in messages]

    assert any(f"agent_started id={instance.id}" in c for c in contents)
    assert any(f"agent_completed id={instance.id}" in c for c in contents)


@pytest.mark.asyncio
async def test_multiple_background_agents_broadcast_independently(monkeypatch):
    _patch_fast_sleep(monkeypatch)

    manager = SubAgentManager(msg_hub=MayaMsgHub())
    first = await manager.spawn(agent_type="coder", task="first", wait=False)
    second = await manager.spawn(agent_type="tester", task="second", wait=False)

    first_msgs = [msg async for msg in manager.subscribe_to_updates(first.id, timeout=2.0)]
    second_msgs = [msg async for msg in manager.subscribe_to_updates(second.id, timeout=2.0)]
    first_contents = [m.content for m in first_msgs]
    second_contents = [m.content for m in second_msgs]

    assert any(f"id={first.id}" in c for c in first_contents)
    assert all(f"id={second.id}" not in c for c in first_contents)
    assert any(f"id={second.id}" in c for c in second_contents)
    assert all(f"id={first.id}" not in c for c in second_contents)
