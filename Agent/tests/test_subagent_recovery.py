import asyncio
from pathlib import Path

import pytest

from core.agents.subagent_architect import ArchitectTask, SubAgentArchitect
from core.agents.subagent_coder import CodingTask, SubAgentCoder
from core.agents.subagent_manager import SubAgentManager
from core.agents.subagent_reviewer import ReviewTask, SubAgentReviewer
from core.agents.worktree_manager import WorktreeContext


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
            }
        )
        self.loaded[step_id] = payload
        return checkpoint_id or "chk_test"

    async def load_checkpoint(self, agent_id):
        return self.loaded.get(agent_id)

    async def mark_terminal(self, task_id, status, reason):
        self.terminals.append(
            {
                "task_id": task_id,
                "status": status,
                "reason": reason,
            }
        )
        return True


class _StaticWorktreeManager:
    def __init__(self, path: Path):
        self.path = str(path)
        self.created = []
        self.cleaned = []

    async def create_worktree(self, *, agent_id, agent_type, task_context):
        self.created.append(
            {
                "agent_id": agent_id,
                "agent_type": agent_type,
                "task_context": task_context,
                "path": self.path,
            }
        )
        return self.path

    async def cleanup_worktree(self, *, worktree_path, status, agent_id):
        self.cleaned.append(
            {
                "worktree_path": worktree_path,
                "status": status,
                "agent_id": agent_id,
            }
        )


def _lineage(task_id: str) -> dict:
    return {
        "parent_handoff_id": f"handoff-{task_id}",
        "delegation_chain_id": f"chain-{task_id}",
        "task_id": task_id,
        "trace_id": f"trace-{task_id}",
        "conversation_id": f"conv-{task_id}",
    }


def _worktree(path: str, task_id: str) -> WorktreeContext:
    return WorktreeContext(
        worktree_id=f"wt-{task_id}",
        task_id=task_id,
        path=path,
        branch=f"subagent/{task_id}/wt",
        base_branch="HEAD",
        status="running",
        created_at=1.0,
        updated_at=1.0,
    )


def _build_runtime_manager(
    *,
    persistence: _FakePersistence,
    worktree_path: Path,
    failure_events: list,
) -> SubAgentManager:
    worktrees = _StaticWorktreeManager(worktree_path)
    manager = SubAgentManager(
        persistence=persistence,
        worktree_manager=worktrees,
        failure_hook=lambda agent_type, agent_id: failure_events.append((agent_type, agent_id)),
    )

    coder = SubAgentCoder()
    reviewer = SubAgentReviewer()
    architect = SubAgentArchitect(subagent_manager=manager)

    async def _lifecycle(agent_type, task_context, resolved_worktree_path):
        worktree = _worktree(str(resolved_worktree_path), str(task_context.get("task_id") or "task"))
        normalized_type = str(agent_type or "").strip().lower()
        if normalized_type == "subagent_coder":
            task = CodingTask.from_task_context(task_context)
            return asyncio.create_task(coder.execute(task, worktree))
        if normalized_type == "subagent_reviewer":
            task = ReviewTask.from_task_context(task_context)
            return asyncio.create_task(reviewer.execute(task, worktree))
        if normalized_type == "subagent_architect":
            task = ArchitectTask.from_task_context(task_context)
            return asyncio.create_task(architect.execute(task, worktree))
        raise AssertionError(f"unsupported agent type: {agent_type}")

    manager._lifecycle_factory = _lifecycle
    return manager


async def _wait_state(manager: SubAgentManager, agent_id: str, *, timeout: float = 1.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        status = manager.get_status(agent_id)
        if status["status"] in {"completed", "failed", "terminated"}:
            return status
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(f"subagent did not finish in time: {agent_id}")
        await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_background_coder_survives_restart_and_resumes(tmp_path):
    persistence = _FakePersistence()
    failure_events = []

    manager_one = SubAgentManager(
        persistence=persistence,
        worktree_manager=_StaticWorktreeManager(tmp_path),
        lifecycle_factory=lambda _t, _ctx, _path: object(),
        failure_hook=lambda agent_type, agent_id: failure_events.append((agent_type, agent_id)),
    )
    background = await manager_one.spawn_background(
        "subagent_coder",
        {
            **_lineage("task-coder-recovery"),
            "file_writes": [{"path": "calc.py", "content": "def add(a, b):\n    return a + b\n"}],
        },
        recoverable=True,
    )

    snapshot = await manager_one.get_background_status(background["task_ref"])
    assert snapshot["status"] == "running"
    assert snapshot["recoverable"] is True

    manager_two = _build_runtime_manager(
        persistence=persistence,
        worktree_path=tmp_path,
        failure_events=failure_events,
    )
    resumed = await manager_two.resume_background(background["task_ref"])
    result = await manager_two.await_completion(background["task_ref"], timeout=1.0)

    assert resumed["agent_id"] == background["task_ref"]
    assert result["status"] == "completed"
    assert result["result"]["changed_files"] == ["calc.py"]
    assert (tmp_path / "calc.py").exists()
    assert failure_events == []


@pytest.mark.asyncio
async def test_architect_plan_resumes_after_restart_and_delegates_coder(tmp_path):
    persistence = _FakePersistence()
    failure_events = []

    manager_one = SubAgentManager(
        persistence=persistence,
        worktree_manager=_StaticWorktreeManager(tmp_path),
        lifecycle_factory=lambda _t, _ctx, _path: object(),
        failure_hook=lambda agent_type, agent_id: failure_events.append((agent_type, agent_id)),
    )
    background = await manager_one.spawn_background(
        "subagent_architect",
        {
            **_lineage("task-architect-recovery"),
            "instruction": "Design and implement a calculator helper",
            "design_doc_path": "docs/calculator.md",
            "design_context": {
                "scope": "calculator helper",
                "target_files": ["src/calc.py"],
            },
            "implementation_steps": [
                {
                    "step_id": "step_1",
                    "title": "write calculator",
                    "description": "create calculator helper",
                    "file_writes": [
                        {
                            "path": "src/calc.py",
                            "content": "def add(a, b):\n    return a + b\n",
                        }
                    ],
                }
            ],
        },
        recoverable=True,
    )

    manager_two = _build_runtime_manager(
        persistence=persistence,
        worktree_path=tmp_path,
        failure_events=failure_events,
    )
    await manager_two.resume_background(background["task_ref"])
    architect_status = await manager_two.await_completion(background["task_ref"], timeout=1.0)
    delegated_coder_id = architect_status["result"]["delegated_subagent"]["agent_id"]
    coder_status = await _wait_state(manager_two, delegated_coder_id, timeout=1.0)

    assert architect_status["status"] == "completed"
    assert coder_status["status"] == "completed"
    assert (tmp_path / "docs" / "calculator.md").exists()
    assert (tmp_path / "src" / "calc.py").exists()
    assert failure_events == []


@pytest.mark.asyncio
async def test_reviewer_resumes_after_restart_from_checkpoint(tmp_path):
    persistence = _FakePersistence()
    failure_events = []
    review_file = tmp_path / "src" / "calc.py"
    review_file.parent.mkdir(parents=True, exist_ok=True)
    review_file.write_text("def add(a, b):\n    print('debug')\n    return a + b\n", encoding="utf-8")

    manager_one = SubAgentManager(
        persistence=persistence,
        worktree_manager=_StaticWorktreeManager(tmp_path),
        lifecycle_factory=lambda _t, _ctx, _path: object(),
        failure_hook=lambda agent_type, agent_id: failure_events.append((agent_type, agent_id)),
    )
    background = await manager_one.spawn_background(
        "subagent_reviewer",
        {
            **_lineage("task-reviewer-recovery"),
            "file_paths": ["src/calc.py"],
        },
        recoverable=True,
    )

    manager_two = _build_runtime_manager(
        persistence=persistence,
        worktree_path=tmp_path,
        failure_events=failure_events,
    )
    await manager_two.resume_background(background["task_ref"])
    reviewer_status = await manager_two.await_completion(background["task_ref"], timeout=1.0)

    comments = reviewer_status["result"]["comments"]
    assert reviewer_status["status"] == "completed"
    assert any(comment["category"] == "debug_artifact" for comment in comments)
    assert failure_events == []
