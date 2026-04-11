import asyncio

import pytest

from core.agents.subagent_manager import SubAgentLifecycleError, SubAgentManager


class _FakeBus:
    def __init__(self):
        self.events = []

    async def publish(self, channel, payload, **kwargs):
        self.events.append((channel, payload, kwargs))
        return {"ok": True}


class _FakePersistence:
    def __init__(self):
        self.checkpoints = []
        self.terminals = []
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

    async def mark_terminal(self, task_id, status, reason):
        self.terminals.append(
            {
                "task_id": task_id,
                "status": status,
                "reason": reason,
            }
        )
        return True

    async def load_checkpoint(self, agent_id):
        return self.loaded.get(agent_id)


class _FakeWorktreeManager:
    def __init__(self):
        self.created = []
        self.cleaned = []

    async def create_worktree(self, *, agent_id, agent_type, task_context):
        path = f"/tmp/{agent_type}-{agent_id}"
        self.created.append(
            {
                "agent_id": agent_id,
                "agent_type": agent_type,
                "task_context": task_context,
                "path": path,
            }
        )
        return path

    async def cleanup_worktree(self, *, worktree_path, status, agent_id):
        self.cleaned.append(
            {
                "worktree_path": worktree_path,
                "status": status,
                "agent_id": agent_id,
            }
        )


def _lineage_context():
    return {
        "parent_handoff_id": "handoff-123",
        "delegation_chain_id": "chain-123",
        "task_id": "task-123",
        "trace_id": "trace-123",
        "conversation_id": "conv-123",
    }


@pytest.mark.asyncio
async def test_spawn_requires_lineage_fields():
    manager = SubAgentManager()

    with pytest.raises(SubAgentLifecycleError) as exc:
        await manager.spawn("subagent_coder", {"task_id": "task-1"})

    assert exc.value.code == "subagent_lineage_required"


@pytest.mark.asyncio
async def test_spawn_wires_worktree_checkpoint_and_progress_event():
    bus = _FakeBus()
    persistence = _FakePersistence()
    worktrees = _FakeWorktreeManager()

    manager = SubAgentManager(
        message_bus=bus,
        persistence=persistence,
        worktree_manager=worktrees,
        lifecycle_factory=lambda _t, _ctx, _path: object(),
    )

    spawned = await manager.spawn("subagent_coder", _lineage_context())
    status = manager.get_status(spawned["agent_id"])

    assert spawned["status"] == "running"
    assert status["status"] == "running"
    assert spawned["worktree_path"].startswith("/tmp/subagent_coder-")
    assert status["parent_handoff_id"] == "handoff-123"
    assert status["delegation_chain_id"] == "chain-123"

    assert len(worktrees.created) == 1
    assert len(persistence.checkpoints) == 1
    assert persistence.checkpoints[0]["payload"]["event"] == "subagent_spawned"
    assert len(bus.events) == 1
    assert bus.events[0][0] == "agent.progress"
    assert bus.events[0][1]["status"] == "running"


@pytest.mark.asyncio
async def test_terminate_is_idempotent_and_cleans_up_worktree():
    bus = _FakeBus()
    persistence = _FakePersistence()
    worktrees = _FakeWorktreeManager()
    manager = SubAgentManager(
        message_bus=bus,
        persistence=persistence,
        worktree_manager=worktrees,
    )

    spawned = await manager.spawn("subagent_reviewer", _lineage_context())
    first = await manager.terminate(spawned["agent_id"])
    second = await manager.terminate(spawned["agent_id"])

    assert first["status"] == "terminated"
    assert second["status"] == "terminated"
    assert len(worktrees.cleaned) == 1
    assert len(persistence.checkpoints) == 2
    assert persistence.checkpoints[1]["payload"]["event"] == "subagent_terminated"
    assert len(bus.events) == 2
    assert bus.events[1][1]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_record_failure_marks_terminal_and_notifies_breaker_hook():
    calls = []

    async def _failure_hook(agent_type, agent_id):
        calls.append((agent_type, agent_id))

    bus = _FakeBus()
    persistence = _FakePersistence()
    worktrees = _FakeWorktreeManager()
    manager = SubAgentManager(
        message_bus=bus,
        persistence=persistence,
        worktree_manager=worktrees,
        failure_hook=_failure_hook,
    )

    spawned = await manager.spawn("subagent_architect", _lineage_context())
    failed = await manager.record_failure(
        spawned["agent_id"],
        error_code="runtime_exception",
        error_detail="boom",
    )

    assert failed["status"] == "failed"
    assert failed["error_code"] == "runtime_exception"
    assert len(worktrees.cleaned) == 1
    assert len(persistence.terminals) == 1
    assert persistence.terminals[0]["status"] == "FAILED"
    assert calls and calls[0][0] == "subagent_architect"
    assert bus.events[-1][1]["status"] == "failed"


@pytest.mark.asyncio
async def test_async_runtime_task_completion_marks_completed_and_persists_result():
    bus = _FakeBus()
    persistence = _FakePersistence()
    worktrees = _FakeWorktreeManager()

    async def _runner():
        await asyncio.sleep(0.01)
        return {
            "summary": "coder completed",
            "changed_files": ["src/generated.py"],
        }

    manager = SubAgentManager(
        message_bus=bus,
        persistence=persistence,
        worktree_manager=worktrees,
        lifecycle_factory=lambda _t, _ctx, _path: asyncio.create_task(_runner()),
    )

    spawned = await manager.spawn("subagent_coder", _lineage_context())
    await asyncio.sleep(0.05)
    status = manager.get_status(spawned["agent_id"])

    assert status["status"] == "completed"
    assert status["metadata"]["result"]["summary"] == "coder completed"
    assert worktrees.cleaned[0]["status"] == "completed"
    assert persistence.terminals[0]["status"] == "COMPLETED"
    assert bus.events[-1][1]["status"] == "completed"


@pytest.mark.asyncio
async def test_spawn_background_returns_trackable_ref_and_completion_status():
    persistence = _FakePersistence()

    async def _runner():
        await asyncio.sleep(0.01)
        return {"summary": "background done"}

    manager = SubAgentManager(
        persistence=persistence,
        lifecycle_factory=lambda _t, _ctx, _path: asyncio.create_task(_runner()),
    )

    background = await manager.spawn_background(
        "subagent_coder",
        _lineage_context(),
    )
    status = await manager.get_background_status(background["task_ref"])
    completed = await manager.await_completion(background["task_ref"], timeout=1.0)

    assert background["task_ref"] == background["agent_id"]
    assert status["status"] in {"running", "completed"}
    assert completed["status"] == "completed"
    assert completed["result"]["summary"] == "background done"


@pytest.mark.asyncio
async def test_resume_background_uses_persistence_bridge_snapshot():
    persistence = _FakePersistence()

    manager_one = SubAgentManager(
        persistence=persistence,
        lifecycle_factory=lambda _t, _ctx, _path: object(),
    )
    background = await manager_one.spawn_background(
        "subagent_coder",
        _lineage_context(),
        recoverable=True,
    )

    async def _runner():
        await asyncio.sleep(0.01)
        return {"summary": "resumed done"}

    manager_two = SubAgentManager(
        persistence=persistence,
        lifecycle_factory=lambda _t, _ctx, _path: asyncio.create_task(_runner()),
    )

    resumed = await manager_two.resume_background(background["task_ref"])
    completed = await manager_two.await_completion(background["task_ref"], timeout=1.0)

    assert resumed["agent_id"] == background["task_ref"]
    assert resumed["metadata"]["recovered_from_agent_id"] == background["task_ref"]
    assert completed["status"] == "completed"
    assert completed["result"]["summary"] == "resumed done"


@pytest.mark.asyncio
async def test_spawn_failure_marks_failed_and_raises():
    manager = SubAgentManager(
        lifecycle_factory=lambda _t, _ctx, _path: (_ for _ in ()).throw(RuntimeError("spawn down")),
    )

    with pytest.raises(RuntimeError):
        await manager.spawn("subagent_coder", _lineage_context())
