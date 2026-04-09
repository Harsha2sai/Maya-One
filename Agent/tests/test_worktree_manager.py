import subprocess
from pathlib import Path

import pytest

from core.agents.worktree_manager import CleanupPolicy, WorktreeManager


def _run(*cmd: str) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run("git", "-C", str(repo), "init")
    _run("git", "-C", str(repo), "config", "user.name", "Test User")
    _run("git", "-C", str(repo), "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _run("git", "-C", str(repo), "add", "README.md")
    _run("git", "-C", str(repo), "commit", "-m", "init")
    return repo


@pytest.mark.asyncio
async def test_worktree_manager_create_status_and_cleanup_success(tmp_path):
    repo = _init_repo(tmp_path)
    manager = WorktreeManager(repo_root=str(repo), worktree_base=str(tmp_path / "wts"))

    ctx = await manager.create_worktree(base_branch="HEAD", task_id="task-1")
    assert Path(ctx.path).exists()
    assert ctx.branch.startswith("subagent/task-1/")

    status = await manager.get_status(ctx.worktree_id)
    assert status.exists is True
    assert status.healthy is True

    await manager.cleanup(ctx.worktree_id, policy=CleanupPolicy.ON_SUCCESS)
    status_after = await manager.get_status(ctx.worktree_id)
    assert status_after.status == "cleaned"
    assert status_after.exists is False


@pytest.mark.asyncio
async def test_worktree_manager_failure_policy_cleanup(tmp_path):
    repo = _init_repo(tmp_path)
    manager = WorktreeManager(repo_root=str(repo), worktree_base=str(tmp_path / "wts"))

    ctx = await manager.create_worktree(base_branch="HEAD", task_id="task-2")
    ctx.status = "running"
    await manager.cleanup(ctx.worktree_id, policy=CleanupPolicy.ON_FAILURE)

    status = await manager.get_status(ctx.worktree_id)
    assert status.exists is True

    ctx.status = "failed"
    await manager.cleanup(ctx.worktree_id, policy=CleanupPolicy.ON_FAILURE)
    status_after = await manager.get_status(ctx.worktree_id)
    assert status_after.exists is False

