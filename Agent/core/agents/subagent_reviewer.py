"""Concrete review subagent runtime for isolated worktree analysis."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.agents.worktree_manager import WorktreeContext

logger = logging.getLogger(__name__)


class ReviewType(str, Enum):
    STANDALONE = "standalone"
    DIFF = "diff"


@dataclass
class ReviewComment:
    path: str
    severity: str
    category: str
    message: str
    line: Optional[int] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "line": self.line,
            "suggestion": self.suggestion,
        }


@dataclass
class DiffAnalysis:
    review_type: str
    files_changed: List[str]
    stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    raw_diff: str = ""
    base_ref: Optional[str] = None
    head_ref: Optional[str] = None
    content_findings: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_type": self.review_type,
            "files_changed": list(self.files_changed or []),
            "stats": dict(self.stats or {}),
            "raw_diff": self.raw_diff,
            "base_ref": self.base_ref,
            "head_ref": self.head_ref,
            "content_findings": dict(self.content_findings or {}),
        }


@dataclass
class ReviewResult:
    success: bool
    review_type: str
    summary: str
    file_paths: List[str]
    comments: List[ReviewComment] = field(default_factory=list)
    analysis: Optional[DiffAnalysis] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "review_type": self.review_type,
            "summary": self.summary,
            "file_paths": list(self.file_paths or []),
            "comments": [comment.to_dict() for comment in self.comments],
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }


@dataclass
class ReviewTask:
    task_id: str
    trace_id: str
    parent_handoff_id: str
    delegation_chain_id: str
    file_paths: List[str] = field(default_factory=list)
    review_type: ReviewType = ReviewType.STANDALONE
    base_ref: Optional[str] = None
    head_ref: Optional[str] = None

    def __post_init__(self) -> None:
        self.file_paths = self._normalize_paths(self.file_paths)
        if not isinstance(self.review_type, ReviewType):
            value = str(self.review_type or ReviewType.STANDALONE.value).strip().lower()
            self.review_type = ReviewType(value or ReviewType.STANDALONE.value)
        self.base_ref = str(self.base_ref or "").strip() or None
        self.head_ref = str(self.head_ref or "").strip() or None

    @classmethod
    def from_task_context(cls, context: Dict[str, Any]) -> "ReviewTask":
        payload = dict(context or {})
        file_paths = payload.get("file_paths")
        if not file_paths:
            file_paths = [
                str(item.get("path") or "").strip()
                for item in (payload.get("file_writes") or [])
                if isinstance(item, dict) and str(item.get("path") or "").strip()
            ]
        return cls(
            task_id=str(payload.get("task_id") or "").strip(),
            trace_id=str(payload.get("trace_id") or "").strip(),
            parent_handoff_id=str(payload.get("parent_handoff_id") or "").strip(),
            delegation_chain_id=str(payload.get("delegation_chain_id") or "").strip(),
            file_paths=file_paths or [],
            review_type=payload.get("review_type") or ReviewType.STANDALONE.value,
            base_ref=payload.get("base_ref"),
            head_ref=payload.get("head_ref"),
        )

    @staticmethod
    def _normalize_paths(values: List[Any]) -> List[str]:
        normalized: List[str] = []
        for value in values or []:
            path = str(value or "").strip()
            if path:
                normalized.append(path)
        return normalized


class SubAgentReviewerError(RuntimeError):
    """Raised when reviewer execution fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SubAgentReviewer:
    """Code review and analysis subagent."""

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
        self._active_task: Optional[ReviewTask] = None

    async def execute(
        self,
        task: ReviewTask,
        worktree_context: WorktreeContext,
        progress_callback: Optional[Callable] = None,
    ) -> ReviewResult:
        self._active_worktree_root = Path(worktree_context.path).resolve()
        self._active_task = task
        if not self._active_worktree_root.exists():
            raise SubAgentReviewerError(
                "worktree_missing",
                f"worktree path does not exist: {self._active_worktree_root}",
            )

        await self._emit_progress(
            task=task,
            status="running",
            phase="subagent_reviewer_start",
            summary="subagent reviewer started",
            percent=10,
            progress_callback=progress_callback,
        )

        try:
            result = await self.review_code(
                str(self._active_worktree_root),
                task.file_paths,
                review_type=task.review_type,
            )
            await self._checkpoint(task, "subagent_reviewer_completed", result.to_dict())
            await self._emit_progress(
                task=task,
                status="completed",
                phase="subagent_reviewer_completed",
                summary=result.summary,
                percent=100,
                progress_callback=progress_callback,
            )
            return result
        except Exception as exc:
            error_code = exc.code if isinstance(exc, SubAgentReviewerError) else "subagent_reviewer_execution_failed"
            await self._checkpoint(
                task,
                "subagent_reviewer_failed",
                {
                    "error_code": str(error_code),
                    "error_detail": str(exc),
                },
            )
            await self._emit_progress(
                task=task,
                status="failed",
                phase="subagent_reviewer_failed",
                summary=f"subagent reviewer failed: {exc}",
                percent=100,
                progress_callback=progress_callback,
            )
            if isinstance(exc, SubAgentReviewerError):
                raise
            raise SubAgentReviewerError(str(error_code), str(exc)) from exc
        finally:
            self._active_worktree_root = None
            self._active_task = None

    async def review_code(
        self,
        worktree_path: str,
        file_paths: List[str],
        review_type: ReviewType = ReviewType.STANDALONE,
    ) -> ReviewResult:
        """Review code in isolated worktree."""
        self._active_worktree_root = Path(worktree_path).resolve()
        if not self._active_worktree_root.exists():
            raise SubAgentReviewerError(
                "worktree_missing",
                f"worktree path does not exist: {self._active_worktree_root}",
            )

        normalized_files = ReviewTask._normalize_paths(file_paths)
        if not normalized_files and review_type != ReviewType.DIFF:
            raise SubAgentReviewerError("review_files_required", "file_paths are required for standalone review")

        await self._emit_inline_progress(
            phase="subagent_reviewer_analyze",
            summary="analyzing review inputs",
            percent=35,
        )

        if review_type == ReviewType.DIFF:
            analysis = await self.analyze_diff(
                self._require_ref("base_ref"),
                self._require_ref("head_ref"),
            )
        else:
            analysis = await self._analyze_files(normalized_files)

        await self._emit_inline_progress(
            phase="subagent_reviewer_comment",
            summary="generating review comments",
            percent=75,
        )
        comments = await self.generate_comments(analysis)

        if comments:
            summary = f"reviewed {len(analysis.files_changed)} files with {len(comments)} comments"
        else:
            summary = f"reviewed {len(analysis.files_changed)} files with no issues found"

        return ReviewResult(
            success=True,
            review_type=analysis.review_type,
            summary=summary,
            file_paths=list(analysis.files_changed or []),
            comments=comments,
            analysis=analysis,
        )

    async def analyze_diff(
        self,
        base_ref: str,
        head_ref: str,
    ) -> DiffAnalysis:
        """Analyze git diff between refs."""
        root = self._active_worktree_root
        if root is None:
            raise SubAgentReviewerError("worktree_not_set", "worktree root is not initialized")

        numstat_command = ["git", "-C", str(root), "diff", "--numstat", base_ref, head_ref]
        diff_command = ["git", "-C", str(root), "diff", "--unified=0", base_ref, head_ref]

        numstat_exit, numstat_stdout, numstat_stderr = await self._run_command(numstat_command)
        if numstat_exit != 0:
            raise SubAgentReviewerError(
                "diff_analysis_failed",
                str(numstat_stderr or numstat_stdout or "git diff --numstat failed"),
            )

        diff_exit, diff_stdout, diff_stderr = await self._run_command(diff_command)
        if diff_exit != 0:
            raise SubAgentReviewerError(
                "diff_analysis_failed",
                str(diff_stderr or diff_stdout or "git diff failed"),
            )

        stats: Dict[str, Dict[str, int]] = {}
        files_changed: List[str] = []
        for line in str(numstat_stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            additions, deletions, path = parts
            normalized_path = str(path or "").strip()
            if not normalized_path:
                continue
            files_changed.append(normalized_path)
            stats[normalized_path] = {
                "additions": self._parse_numstat_value(additions),
                "deletions": self._parse_numstat_value(deletions),
            }

        content_findings = await self._scan_files(files_changed)
        return DiffAnalysis(
            review_type=ReviewType.DIFF.value,
            files_changed=files_changed,
            stats=stats,
            raw_diff=str(diff_stdout or ""),
            base_ref=base_ref,
            head_ref=head_ref,
            content_findings=content_findings,
        )

    async def generate_comments(
        self,
        analysis: DiffAnalysis,
    ) -> List[ReviewComment]:
        """Generate structured review comments."""
        comments: List[ReviewComment] = []
        for path in analysis.files_changed:
            for finding in analysis.content_findings.get(path, []):
                comments.append(
                    ReviewComment(
                        path=path,
                        severity=str(finding.get("severity") or "info"),
                        category=str(finding.get("category") or "general"),
                        message=str(finding.get("message") or "review note"),
                        line=finding.get("line"),
                        suggestion=finding.get("suggestion"),
                    )
                )
        return comments

    async def _analyze_files(self, file_paths: List[str]) -> DiffAnalysis:
        findings = await self._scan_files(file_paths)
        return DiffAnalysis(
            review_type=ReviewType.STANDALONE.value,
            files_changed=list(file_paths or []),
            content_findings=findings,
        )

    async def _scan_files(self, file_paths: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        root = self._active_worktree_root
        if root is None:
            raise SubAgentReviewerError("worktree_not_set", "worktree root is not initialized")

        findings: Dict[str, List[Dict[str, Any]]] = {}
        for file_path in file_paths or []:
            resolved = (root / file_path).resolve()
            if not self._is_within_root(resolved, root):
                raise SubAgentReviewerError(
                    "path_escape_denied",
                    f"refusing to review outside worktree: {file_path}",
                )
            if not resolved.exists():
                raise SubAgentReviewerError("review_file_missing", f"review target not found: {file_path}")
            if not resolved.is_file():
                continue

            file_findings: List[Dict[str, Any]] = []
            for line_number, line in enumerate(resolved.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.strip()
                if "TODO" in line or "FIXME" in line:
                    file_findings.append(
                        {
                            "line": line_number,
                            "severity": "warning",
                            "category": "todo_marker",
                            "message": "left a TODO/FIXME marker in reviewed code",
                            "suggestion": "resolve or track the follow-up explicitly before merge",
                        }
                    )
                if "print(" in line or "console.log(" in line:
                    file_findings.append(
                        {
                            "line": line_number,
                            "severity": "warning",
                            "category": "debug_artifact",
                            "message": "debug output remains in the reviewed code path",
                            "suggestion": "remove debug logging or replace it with structured logging",
                        }
                    )
                if stripped == "except:":
                    file_findings.append(
                        {
                            "line": line_number,
                            "severity": "critical",
                            "category": "bare_except",
                            "message": "bare except hides the failure class and broadens retries incorrectly",
                            "suggestion": "catch the expected exception type explicitly",
                        }
                    )
            findings[file_path] = file_findings
        return findings

    async def _emit_inline_progress(self, *, phase: str, summary: str, percent: int) -> None:
        task = self._active_task
        if task is None:
            return
        await self._emit_progress(
            task=task,
            status="running",
            phase=phase,
            summary=summary,
            percent=percent,
            progress_callback=None,
        )

    async def _emit_progress(
        self,
        *,
        task: ReviewTask,
        status: str,
        phase: str,
        summary: str,
        percent: int,
        progress_callback: Optional[Callable],
    ) -> None:
        payload = {
            "phase": phase,
            "agent": "subagent_reviewer",
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

    async def _checkpoint(self, task: ReviewTask, event: str, payload: Dict[str, Any]) -> None:
        save_checkpoint = getattr(self._persistence, "save_checkpoint", None)
        if not callable(save_checkpoint) or not task.task_id:
            return
        maybe = save_checkpoint(
            task_id=task.task_id,
            step_id="subagent_reviewer",
            payload={
                "event": event,
                "agent": "subagent_reviewer",
                "parent_handoff_id": task.parent_handoff_id,
                "delegation_chain_id": task.delegation_chain_id,
                "result": json.loads(json.dumps(payload, ensure_ascii=True)),
            },
        )
        if asyncio.iscoroutine(maybe):
            await maybe

    async def _run_command(self, command: List[str]):
        root = self._active_worktree_root
        result = self._command_runner(command, str(root) if root else "")
        if asyncio.iscoroutine(result):
            result = await result
        return result

    def _require_ref(self, field_name: str) -> str:
        task = self._active_task
        value = getattr(task, field_name, None) if task is not None else None
        normalized = str(value or "").strip()
        if not normalized:
            raise SubAgentReviewerError("diff_ref_required", f"{field_name} is required for diff review")
        return normalized

    @staticmethod
    def _parse_numstat_value(value: str) -> int:
        text = str(value or "").strip()
        if text == "-":
            return 0
        return int(text or "0")

    @staticmethod
    def _is_within_root(target: Path, root: Path) -> bool:
        target_s = str(target)
        root_s = str(root)
        if target_s == root_s:
            return True
        return target_s.startswith(root_s + "/")

    @staticmethod
    def _default_command_runner(command: List[str], cwd: str):
        proc = subprocess.run(command, cwd=cwd or None, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr
