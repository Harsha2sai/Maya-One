from pathlib import Path

import pytest

from core.agents.subagent_coder import CodingTask, SubAgentCoder, SubAgentCoderError
from core.agents.worktree_manager import WorktreeContext


class _FakeBus:
    def __init__(self):
        self.events = []

    async def publish(self, channel, payload, **kwargs):
        self.events.append((channel, payload, kwargs))
        return {"ok": True}


class _FakePersistence:
    def __init__(self):
        self.checkpoints = []

    async def save_checkpoint(self, task_id, step_id, payload, checkpoint_id=None, ts=None):
        self.checkpoints.append(
            {
                "task_id": task_id,
                "step_id": step_id,
                "payload": payload,
            }
        )
        return checkpoint_id or "chk_test"


def _worktree(tmp_path: Path) -> WorktreeContext:
    return WorktreeContext(
        worktree_id="wt_1",
        task_id="task-1",
        path=str(tmp_path),
        branch="subagent/task-1/wt_1",
        base_branch="HEAD",
        status="running",
        created_at=1.0,
        updated_at=1.0,
    )


@pytest.mark.asyncio
async def test_subagent_coder_executes_writes_and_checkpoints(tmp_path):
    bus = _FakeBus()
    persistence = _FakePersistence()
    coder = SubAgentCoder(message_bus=bus, persistence=persistence)

    task = CodingTask(
        task_id="task-1",
        trace_id="trace-1",
        parent_handoff_id="handoff-1",
        delegation_chain_id="chain-1",
        instruction="write files",
        file_writes=[
            {"path": "src/a.py", "content": "print('a')\n"},
            {"path": "src/b.py", "content": "print('b')\n"},
        ],
    )

    result = await coder.execute(task, _worktree(tmp_path))
    assert result.success is True
    assert sorted(result.changed_files) == ["src/a.py", "src/b.py"]
    assert (tmp_path / "src" / "a.py").read_text(encoding="utf-8") == "print('a')\n"
    assert (tmp_path / "src" / "b.py").read_text(encoding="utf-8") == "print('b')\n"
    assert any(c["payload"]["event"] == "subagent_coder_completed" for c in persistence.checkpoints)
    assert any(event[1]["status"] == "completed" for event in bus.events)


@pytest.mark.asyncio
async def test_subagent_coder_raises_when_tests_fail(tmp_path):
    bus = _FakeBus()
    persistence = _FakePersistence()

    def _runner(_command, _cwd):
        return 1, "failed", "assertion"

    coder = SubAgentCoder(
        message_bus=bus,
        persistence=persistence,
        command_runner=_runner,
    )
    task = CodingTask(
        task_id="task-2",
        trace_id="trace-2",
        parent_handoff_id="handoff-2",
        delegation_chain_id="chain-2",
        test_pattern="tests/test_dummy.py",
    )

    with pytest.raises(SubAgentCoderError) as exc:
        await coder.execute(task, _worktree(tmp_path))

    assert exc.value.code == "subagent_coder_tests_failed"
    assert any(c["payload"]["event"] == "subagent_coder_failed" for c in persistence.checkpoints)
    assert any(event[1]["status"] == "failed" for event in bus.events)


@pytest.mark.asyncio
async def test_subagent_coder_denies_path_escape(tmp_path):
    coder = SubAgentCoder()
    task = CodingTask(
        task_id="task-3",
        trace_id="trace-3",
        parent_handoff_id="handoff-3",
        delegation_chain_id="chain-3",
        file_writes=[{"path": "../escape.py", "content": "x=1\n"}],
    )

    with pytest.raises(SubAgentCoderError) as exc:
        await coder.execute(task, _worktree(tmp_path))

    assert exc.value.code == "path_escape_denied"

