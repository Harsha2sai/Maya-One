import logging
import subprocess
from pathlib import Path

from .types import WorktreeError

logger = logging.getLogger(__name__)

BASE_PATH = Path("/tmp/maya-worktrees")


class WorktreeManager:
    def __init__(self, base_path: Path = BASE_PATH):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def create(self, agent_id: str) -> Path:
        worktree_path = self.base_path / agent_id
        branch_name = f"agent-{agent_id}"

        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise WorktreeError(f"Failed to create worktree: {result.stderr}")

        logger.info("worktree_created agent_id=%s path=%s", agent_id, worktree_path)
        return worktree_path

    async def destroy(self, agent_id: str):
        worktree_path = self.base_path / agent_id
        branch_name = f"agent-{agent_id}"

        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            capture_output=True,
            text=True,
        )
        logger.info("worktree_destroyed agent_id=%s", agent_id)

    async def get_diff(self, agent_id: str) -> str:
        worktree_path = self.base_path / agent_id
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
        )
        return result.stdout
