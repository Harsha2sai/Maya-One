"""Concrete coding subagent runtime for isolated worktree execution."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.agents.worktree_manager import WorktreeContext

logger = logging.getLogger(__name__)


@dataclass
class CodingFileWrite:
    path: str
    content: str


@dataclass
class CodingTask:
    task_id: str
    trace_id: str
    parent_handoff_id: str
    delegation_chain_id: str
    instruction: str = ""
    file_writes: List[CodingFileWrite] = field(default_factory=list)
    test_pattern: Optional[str] = None

    def __post_init__(self) -> None:
        self.file_writes = self._normalize_file_writes(self.file_writes)

    @classmethod
    def from_task_context(cls, context: Dict[str, Any]) -> "CodingTask":
        payload = dict(context or {})
        return cls(
            task_id=str(payload.get("task_id") or "").strip(),
            trace_id=str(payload.get("trace_id") or "").strip(),
            parent_handoff_id=str(payload.get("parent_handoff_id") or "").strip(),
            delegation_chain_id=str(payload.get("delegation_chain_id") or "").strip(),
            instruction=str(payload.get("instruction") or "").strip(),
            file_writes=payload.get("file_writes") or [],
            test_pattern=str(payload.get("test_pattern") or "").strip() or None,
        )

    @staticmethod
    def _normalize_file_writes(values: List[Any]) -> List[CodingFileWrite]:
        writes: List[CodingFileWrite] = []
        for item in values or []:
            if isinstance(item, CodingFileWrite):
                if item.path:
                    writes.append(item)
                continue
            if isinstance(item, dict):
                path = str(item.get("path") or "").strip()
                if not path:
                    continue
                writes.append(
                    CodingFileWrite(
                        path=path,
                        content=str(item.get("content") or ""),
                    )
                )
        return writes


@dataclass
class TestResult:
    success: bool
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float


@dataclass
class CodingResult:
    success: bool
    changed_files: List[str]
    summary: str
    test_result: Optional[TestResult] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "success": self.success,
            "changed_files": list(self.changed_files or []),
            "summary": self.summary,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }
        if self.test_result:
            payload["test_result"] = {
                "success": self.test_result.success,
                "command": self.test_result.command,
                "exit_code": self.test_result.exit_code,
                "stdout": self.test_result.stdout,
                "stderr": self.test_result.stderr,
                "duration_ms": self.test_result.duration_ms,
            }
        return payload


class SubAgentCoderError(RuntimeError):
    """Raised when coding subagent execution fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SubAgentCoder:
    """Code generation and modification subagent."""

    def __init__(
        self,
        *,
        message_bus: Any = None,
        persistence: Any = None,
        command_runner: Optional[Callable[[List[str], str], Any]] = None,
    ) -> None:
        self._message_bus = message_bus
        self._persistence = persistence
        self._command_runner = command_runner or self._default_command_runner
        self._active_worktree_root: Optional[Path] = None

    async def execute(
        self,
        task: CodingTask,
        worktree_context: WorktreeContext,
        progress_callback: Optional[Callable] = None,
    ) -> CodingResult:
        """Execute coding task in isolated worktree."""
        self._active_worktree_root = Path(worktree_context.path).resolve()
        if not self._active_worktree_root.exists():
            raise SubAgentCoderError(
                "worktree_missing",
                f"worktree path does not exist: {self._active_worktree_root}",
            )

        await self._emit_progress(
            task=task,
            status="running",
            phase="subagent_coder_start",
            summary="subagent coder started",
            percent=10,
            progress_callback=progress_callback,
        )

        changed_files: List[str] = []
        test_result: Optional[TestResult] = None
        try:
            if task.file_writes:
                step = max(1, int(50 / max(1, len(task.file_writes))))
                for idx, item in enumerate(task.file_writes, start=1):
                    await self.write_file(item.path, item.content)
                    changed_files.append(item.path)
                    await self._emit_progress(
                        task=task,
                        status="running",
                        phase="subagent_coder_write",
                        summary=f"updated {item.path}",
                        percent=min(70, 20 + (idx * step)),
                        progress_callback=progress_callback,
                    )

            if task.test_pattern:
                await self._emit_progress(
                    task=task,
                    status="running",
                    phase="subagent_coder_test",
                    summary=f"running tests: {task.test_pattern}",
                    percent=80,
                    progress_callback=progress_callback,
                )
                test_result = await self.run_tests(task.test_pattern)
                if not test_result.success:
                    raise SubAgentCoderError(
                        "subagent_coder_tests_failed",
                        f"tests failed with exit code {test_result.exit_code}",
                    )

            result = CodingResult(
                success=True,
                changed_files=changed_files,
                summary="coding task completed",
                test_result=test_result,
            )
            await self._checkpoint(task, "subagent_coder_completed", result.to_dict())
            await self._emit_progress(
                task=task,
                status="completed",
                phase="subagent_coder_completed",
                summary=result.summary,
                percent=100,
                progress_callback=progress_callback,
            )
            return result
        except Exception as exc:
            error_code = exc.code if isinstance(exc, SubAgentCoderError) else "subagent_coder_execution_failed"
            await self._checkpoint(
                task,
                "subagent_coder_failed",
                {
                    "error_code": str(error_code),
                    "error_detail": str(exc),
                    "changed_files": changed_files,
                },
            )
            await self._emit_progress(
                task=task,
                status="failed",
                phase="subagent_coder_failed",
                summary=f"subagent coder failed: {exc}",
                percent=100,
                progress_callback=progress_callback,
            )
            if isinstance(exc, SubAgentCoderError):
                raise
            raise SubAgentCoderError(str(error_code), str(exc)) from exc
        finally:
            self._active_worktree_root = None

    async def write_file(self, path: str, content: str) -> None:
        """Write code to worktree."""
        root = self._active_worktree_root
        if root is None:
            raise SubAgentCoderError("worktree_not_set", "worktree root is not initialized")

        normalized = str(path or "").strip()
        if not normalized:
            raise SubAgentCoderError("invalid_path", "target path is required")

        candidate = Path(normalized)
        target = candidate if candidate.is_absolute() else (root / candidate)
        target = target.resolve()
        if not self._is_within_root(target, root):
            raise SubAgentCoderError(
                "path_escape_denied",
                f"refusing to write outside worktree: {normalized}",
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    async def run_tests(self, test_pattern: str) -> TestResult:
        """Execute tests in worktree."""
        root = self._active_worktree_root
        if root is None:
            raise SubAgentCoderError("worktree_not_set", "worktree root is not initialized")

        pattern = str(test_pattern or "").strip()
        if not pattern:
            raise SubAgentCoderError("invalid_test_pattern", "test pattern is required")

        command = ["pytest", pattern, "-q"]
        started = time.perf_counter()
        result = self._command_runner(command, str(root))
        if asyncio.iscoroutine(result):
            result = await result
        exit_code, stdout, stderr = result
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return TestResult(
            success=int(exit_code) == 0,
            command=" ".join(command),
            exit_code=int(exit_code),
            stdout=str(stdout or ""),
            stderr=str(stderr or ""),
            duration_ms=elapsed_ms,
        )

    @staticmethod
    def _is_within_root(target: Path, root: Path) -> bool:
        root_s = str(root)
        target_s = str(target)
        if target_s == root_s:
            return True
        return target_s.startswith(root_s + os.sep)

    @staticmethod
    def _default_command_runner(command: List[str], cwd: str):
        proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    async def _emit_progress(
        self,
        *,
        task: CodingTask,
        status: str,
        phase: str,
        summary: str,
        percent: int,
        progress_callback: Optional[Callable],
    ) -> None:
        payload = {
            "phase": phase,
            "agent": "subagent_coder",
            "status": status,
            "percent": percent,
            "summary": summary,
            "task_id": task.task_id,
            "trace_id": task.trace_id,
            "parent_handoff_id": task.parent_handoff_id,
            "delegation_chain_id": task.delegation_chain_id,
        }
        if callable(progress_callback):
            maybe = progress_callback(payload)
            if asyncio.iscoroutine(maybe):
                await maybe

        publish = getattr(self._message_bus, "publish", None)
        if not callable(publish):
            return
        maybe = publish(
            "agent.progress",
            payload,
            trace_id=task.trace_id,
            handoff_id=task.parent_handoff_id,
            task_id=task.task_id,
            metadata={"delegation_chain_id": task.delegation_chain_id},
        )
        if asyncio.iscoroutine(maybe):
            await maybe

    async def _checkpoint(self, task: CodingTask, event: str, payload: Dict[str, Any]) -> None:
        save_checkpoint = getattr(self._persistence, "save_checkpoint", None)
        if not callable(save_checkpoint) or not task.task_id:
            return
        maybe = save_checkpoint(
            task_id=task.task_id,
            step_id="subagent_coder",
            payload={
                "event": event,
                "agent": "subagent_coder",
                "parent_handoff_id": task.parent_handoff_id,
                "delegation_chain_id": task.delegation_chain_id,
                "result": json.loads(json.dumps(payload, ensure_ascii=True)),
            },
        )
        if asyncio.iscoroutine(maybe):
            await maybe
