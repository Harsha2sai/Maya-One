import asyncio
from types import SimpleNamespace

import pytest

from core.agents.contracts import AgentCapabilityMatch, AgentHandoffRequest, AgentHandoffResult
from core.agents.handoff_manager import HandoffManager
from core.agents.subagent import SubAgentManager, WorktreeManager
from core.agents.subagent.manager import MAX_CONCURRENT
from core.agents.subagent.types import SubAgentCapacityError, SubAgentInstance, SubAgentStatus
from core.messaging import MayaMsgHub


@pytest.mark.asyncio
async def test_spawn_wait_true_completes():
    manager = SubAgentManager(msg_hub=MayaMsgHub())
    instance = await manager.spawn(agent_type="coder", task="write a function", wait=True)
    assert instance.status == SubAgentStatus.COMPLETED
    assert instance.completed_at is not None


@pytest.mark.asyncio
async def test_spawn_wait_false_transitions_to_completed():
    manager = SubAgentManager(msg_hub=MayaMsgHub())
    instance = await manager.spawn(agent_type="reviewer", task="review this", wait=False)
    assert instance.status in {SubAgentStatus.PENDING, SubAgentStatus.RUNNING, SubAgentStatus.COMPLETED}

    deadline = asyncio.get_running_loop().time() + 2.0
    latest = instance
    while asyncio.get_running_loop().time() < deadline:
        latest = await manager.check_result(instance.id)
        if latest and latest.status == SubAgentStatus.COMPLETED:
            break
        await asyncio.sleep(0.05)

    assert latest is not None
    assert latest.status == SubAgentStatus.COMPLETED


@pytest.mark.asyncio
async def test_check_result_returns_instance():
    manager = SubAgentManager(msg_hub=MayaMsgHub())
    instance = await manager.spawn(agent_type="tester", task="create tests", wait=False)
    fetched = await manager.check_result(instance.id)
    assert fetched is instance


@pytest.mark.asyncio
async def test_spawn_raises_capacity_error_when_limit_exceeded():
    manager = SubAgentManager(msg_hub=MayaMsgHub())
    for idx in range(MAX_CONCURRENT):
        manager.active[f"agent-{idx}"] = SubAgentInstance(
            id=f"agent-{idx}",
            agent_type="coder",
            task="x",
            status=SubAgentStatus.RUNNING,
        )

    with pytest.raises(SubAgentCapacityError):
        await manager.spawn(agent_type="coder", task="overflow", wait=False)


@pytest.mark.asyncio
async def test_send_message_unknown_agent_raises_key_error():
    manager = SubAgentManager(msg_hub=MayaMsgHub())
    with pytest.raises(KeyError):
        await manager.send_message("missing-agent", "hello")


@pytest.mark.asyncio
async def test_worktree_create_destroy_cycle(monkeypatch, tmp_path):
    calls = []

    def _fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("core.agents.subagent.worktree.subprocess.run", _fake_run)
    manager = WorktreeManager(base_path=tmp_path)
    worktree_path = await manager.create("agent-1")
    await manager.destroy("agent-1")

    assert str(worktree_path).endswith("agent-1")
    assert calls[0][0][:4] == ["git", "worktree", "add", "-b"]
    assert calls[1][0][:3] == ["git", "worktree", "remove"]
    assert calls[2][0][:3] == ["git", "branch", "-D"]


def _request(**overrides) -> AgentHandoffRequest:
    payload = {
        "handoff_id": "h-1",
        "trace_id": "t-1",
        "conversation_id": "c-1",
        "task_id": None,
        "parent_agent": "maya",
        "active_agent": "maya",
        "target_agent": "research",
        "intent": "research",
        "user_text": "who is grace hopper",
        "context_slice": "research ask",
        "execution_mode": "inline",
        "delegation_depth": 0,
        "max_depth": 1,
        "handoff_reason": "test",
        "metadata": {"user_id": "u1"},
    }
    payload.update(overrides)
    return AgentHandoffRequest(**payload)


@pytest.mark.asyncio
async def test_handoff_manager_bridge_legacy_paths_work_without_explicit_subagent_manager():
    class _Registry:
        async def can_accept(self, request):
            return AgentCapabilityMatch(
                agent_name=request.target_agent,
                confidence=1.0,
                reason="ok",
                hard_constraints_passed=True,
            )

        async def handle(self, request):
            return AgentHandoffResult(
                handoff_id=request.handoff_id,
                trace_id=request.trace_id,
                source_agent=request.target_agent,
                status="completed",
                user_visible_text="done",
                voice_text="done",
                structured_payload={"ok": True},
                next_action="continue",
                error_code=None,
                error_detail=None,
            )

    manager = HandoffManager(_Registry(), subagent_manager=None)
    result = await manager.delegate(_request(target_agent="research"))
    assert result.status == "completed"
