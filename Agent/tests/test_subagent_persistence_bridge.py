import pytest

from core.agents.subagent_persistence_bridge import RecoveryPolicy, SubagentPersistenceBridge


class _FakePersistence:
    def __init__(self):
        self.checkpoints = []
        self.loaded = {}

    async def save_checkpoint(self, task_id, step_id, payload, checkpoint_id=None, ts=None):
        self.checkpoints.append(
            {
                "task_id": task_id,
                "step_id": step_id,
                "payload": payload,
                "checkpoint_id": checkpoint_id,
                "ts": ts,
            }
        )
        self.loaded[step_id] = payload
        return checkpoint_id or "chk_test"

    async def load_checkpoint(self, agent_id):
        return self.loaded.get(agent_id)


class _FakeSubAgentManager:
    def __init__(self):
        self.calls = []

    async def spawn(self, agent_type, task_context, worktree_path=None):
        self.calls.append((agent_type, task_context, worktree_path))
        return {
            "agent_id": "subag_resumed_1",
            "agent_type": agent_type,
            "status": "running",
            "task_context": task_context,
            "worktree_path": worktree_path,
            "metadata": {},
        }


def _state(**overrides):
    payload = {
        "agent_id": "subag_123",
        "agent_type": "subagent_coder",
        "status": "running",
        "task_id": "task-123",
        "trace_id": "trace-123",
        "conversation_id": "conv-123",
        "parent_handoff_id": "handoff-123",
        "delegation_chain_id": "chain-123",
        "worktree_path": "/tmp/subag_123",
        "task_context": {
            "parent_handoff_id": "handoff-123",
            "delegation_chain_id": "chain-123",
            "task_id": "task-123",
            "trace_id": "trace-123",
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_save_checkpoint_persists_recovery_snapshot():
    persistence = _FakePersistence()
    bridge = SubagentPersistenceBridge(persistence=persistence)

    await bridge.mark_recoverable("subag_123", RecoveryPolicy.ON_FAILURE)
    await bridge.save_checkpoint("subag_123", _state())

    assert len(persistence.checkpoints) == 2
    assert persistence.checkpoints[-1]["payload"]["event"] == "subagent_recovery_checkpoint"
    assert persistence.checkpoints[-1]["payload"]["recovery_policy"] == "on_failure"


@pytest.mark.asyncio
async def test_resume_from_checkpoint_returns_in_memory_state_without_manager():
    bridge = SubagentPersistenceBridge()

    await bridge.mark_recoverable("subag_123", RecoveryPolicy.ALWAYS)
    await bridge.save_checkpoint("subag_123", _state())
    resumed = await bridge.resume_from_checkpoint("subag_123")

    assert resumed is not None
    assert resumed["agent_id"] == "subag_123"
    assert resumed["recovered"] is True
    assert resumed["recovery_policy"] == "always"
    assert resumed["state"]["status"] == "running"


@pytest.mark.asyncio
async def test_resume_from_checkpoint_respawns_through_manager():
    persistence = _FakePersistence()
    manager = _FakeSubAgentManager()
    bridge = SubagentPersistenceBridge(
        persistence=persistence,
        subagent_manager=manager,
    )

    await bridge.mark_recoverable("subag_123", RecoveryPolicy.ALWAYS)
    await bridge.save_checkpoint("subag_123", _state())
    resumed = await bridge.resume_from_checkpoint("subag_123")

    assert resumed is not None
    assert resumed["agent_id"] == "subag_resumed_1"
    assert resumed["metadata"]["recovered_from_agent_id"] == "subag_123"
    assert resumed["metadata"]["recovery_policy"] == "always"
    assert manager.calls[0][0] == "subagent_coder"
    assert manager.calls[0][2] == "/tmp/subag_123"


@pytest.mark.asyncio
async def test_resume_skips_non_recoverable_or_terminal_states():
    bridge = SubagentPersistenceBridge()

    await bridge.save_checkpoint("subag_123", _state(status="completed"))
    assert await bridge.resume_from_checkpoint("subag_123") is None

    await bridge.mark_recoverable("subag_456", RecoveryPolicy.NEVER)
    await bridge.save_checkpoint("subag_456", _state(agent_id="subag_456"))
    assert await bridge.resume_from_checkpoint("subag_456") is None
