"""Git worktree isolation manager for subagent runtime contexts."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CleanupPolicy(str, Enum):
    ON_SUCCESS = "on_success"
    ON_FAILURE = "on_failure"
    NEVER = "never"


@dataclass
class WorktreeContext:
    worktree_id: str
    task_id: str
    path: str
    branch: str
    base_branch: str
    status: str
    created_at: float
    updated_at: float
    last_error: Optional[str] = None


@dataclass
class WorktreeStatus:
    worktree_id: str
    task_id: str
    path: str
    branch: str
    base_branch: str
    status: str
    exists: bool
    healthy: bool
    updated_at: float
    last_error: Optional[str] = None


class WorktreeManagerError(RuntimeError):
    """Raised when worktree operations fail."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class WorktreeManager:
    """Git worktree isolation for subagent contexts."""

    CleanupPolicy = CleanupPolicy

    def __init__(
        self,
        *,
        repo_root: Optional[str] = None,
        worktree_base: Optional[str] = None,
    ) -> None:
        self.repo_root = Path(repo_root or os.getcwd()).resolve()
        self.worktree_base = Path(worktree_base or (self.repo_root / ".maya_worktrees")).resolve()
        self._contexts: Dict[str, WorktreeContext] = {}
        self._by_path: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def create_worktree(
        self,
        base_branch: str,
        task_id: str,
        worktree_base: Optional[str] = None,
    ) -> WorktreeContext:
        """Create isolated git worktree for subagent."""
        base = Path(worktree_base).resolve() if worktree_base else self.worktree_base
        base.mkdir(parents=True, exist_ok=True)
        branch_base = self._sanitize_task_id(task_id)
        worktree_id = f"wt_{uuid.uuid4().hex[:10]}"
        branch_name = f"subagent/{branch_base}/{worktree_id}"
        path = str((base / f"{branch_base}-{worktree_id}").resolve())

        await self._git(
            "worktree",
            "add",
            "-b",
            branch_name,
            path,
            str(base_branch or "HEAD"),
        )

        now = float(time.time())
        ctx = WorktreeContext(
            worktree_id=worktree_id,
            task_id=str(task_id or "").strip() or "task",
            path=path,
            branch=branch_name,
            base_branch=str(base_branch or "HEAD"),
            status="running",
            created_at=now,
            updated_at=now,
            last_error=None,
        )
        async with self._lock:
            self._contexts[worktree_id] = ctx
            self._by_path[path] = worktree_id
        logger.info("worktree_created id=%s branch=%s path=%s", worktree_id, branch_name, path)
        return ctx

    async def cleanup(
        self,
        worktree_id: str,
        policy: CleanupPolicy = CleanupPolicy.ON_SUCCESS,
    ) -> None:
        """Remove worktree based on policy."""
        normalized = str(worktree_id or "").strip()
        async with self._lock:
            ctx = self._contexts.get(normalized)
        if ctx is None:
            raise LookupError(f"worktree_not_found:{normalized}")

        if policy == CleanupPolicy.NEVER:
            logger.info("worktree_cleanup_skipped policy=never id=%s", normalized)
            return

        if policy == CleanupPolicy.ON_FAILURE and str(ctx.status).lower() != "failed":
            logger.info("worktree_cleanup_skipped policy=on_failure status=%s id=%s", ctx.status, normalized)
            return

        if policy == CleanupPolicy.ON_SUCCESS and str(ctx.status).lower() == "failed":
            logger.info("worktree_cleanup_skipped policy=on_success status=failed id=%s", normalized)
            return

        remove_error = None
        try:
            await self._git("worktree", "remove", "--force", ctx.path)
        except Exception as err:
            remove_error = str(err)
            logger.warning("worktree_remove_failed id=%s error=%s", normalized, remove_error)

        try:
            await self._git("branch", "-D", ctx.branch)
        except Exception as err:
            logger.info("worktree_branch_delete_skipped id=%s branch=%s error=%s", normalized, ctx.branch, err)

        try:
            await self._git("worktree", "prune")
        except Exception as err:
            logger.debug("worktree_prune_failed error=%s", err)

        ctx.status = "cleaned"
        ctx.updated_at = float(time.time())
        ctx.last_error = remove_error
        logger.info("worktree_cleaned id=%s path=%s", normalized, ctx.path)

    async def get_status(self, worktree_id: str) -> WorktreeStatus:
        """Check worktree health."""
        normalized = str(worktree_id or "").strip()
        async with self._lock:
            ctx = self._contexts.get(normalized)
        if ctx is None:
            raise LookupError(f"worktree_not_found:{normalized}")

        exists = Path(ctx.path).exists()
        healthy = False
        if exists:
            try:
                await self._git("-C", ctx.path, "rev-parse", "--is-inside-work-tree")
                healthy = True
            except Exception as err:
                ctx.last_error = str(err)
                healthy = False
        return WorktreeStatus(
            worktree_id=ctx.worktree_id,
            task_id=ctx.task_id,
            path=ctx.path,
            branch=ctx.branch,
            base_branch=ctx.base_branch,
            status=ctx.status,
            exists=exists,
            healthy=healthy,
            updated_at=ctx.updated_at,
            last_error=ctx.last_error,
        )

    async def create(self, *, agent_id: str, agent_type: str, task_context: Dict[str, str]):
        """Compatibility shim for SubAgentManager.create(...)."""
        base_branch = str(task_context.get("base_branch") or "HEAD")
        task_id = str(task_context.get("task_id") or agent_id or "task")
        ctx = await self.create_worktree(base_branch=base_branch, task_id=task_id)
        return ctx.path

    async def cleanup_worktree(self, *, worktree_path: str, status: str, agent_id: str) -> None:
        """Compatibility shim for SubAgentManager.cleanup_worktree(...)."""
        normalized_path = str(worktree_path or "").strip()
        async with self._lock:
            worktree_id = self._by_path.get(normalized_path)
            ctx = self._contexts.get(worktree_id) if worktree_id else None
        if not worktree_id or ctx is None:
            return
        ctx.status = str(status or ctx.status)
        policy = CleanupPolicy.ON_FAILURE if str(status or "").strip().lower() == "failed" else CleanupPolicy.ON_SUCCESS
        await self.cleanup(worktree_id, policy=policy)

    @staticmethod
    def _sanitize_task_id(task_id: str) -> str:
        value = str(task_id or "").strip().lower() or "task"
        value = re.sub(r"[^a-z0-9._-]+", "-", value)
        value = re.sub(r"-{2,}", "-", value).strip("-")
        return value[:48] or "task"

    async def _git(self, *args: str) -> str:
        cmd = ["git", "-C", str(self.repo_root), *args]

        def _run() -> str:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise WorktreeManagerError(
                    "worktree_git_failed",
                    f"command={' '.join(cmd)} stderr={proc.stderr.strip()}",
                )
            return (proc.stdout or "").strip()

        return await asyncio.to_thread(_run)
