"""Concrete architect subagent runtime for planning and delegated implementation."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.agents.subagent_manager import SubAgentManager
from core.agents.worktree_manager import WorktreeContext


@dataclass
class DesignContext:
    scope: str = ""
    constraints: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    target_files: List[str] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "DesignContext":
        payload = dict(payload or {})
        return cls(
            scope=str(payload.get("scope") or "").strip(),
            constraints=cls._normalize_strings(payload.get("constraints")),
            assumptions=cls._normalize_strings(payload.get("assumptions")),
            target_files=cls._normalize_strings(payload.get("target_files")),
        )

    @staticmethod
    def _normalize_strings(values: Any) -> List[str]:
        result: List[str] = []
        for value in values or []:
            text = str(value or "").strip()
            if text:
                result.append(text)
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "constraints": list(self.constraints or []),
            "assumptions": list(self.assumptions or []),
            "target_files": list(self.target_files or []),
        }


@dataclass
class DesignDocument:
    title: str
    requirements: str
    summary: str
    architecture: List[str]
    risks: List[str] = field(default_factory=list)
    design_doc_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "requirements": self.requirements,
            "summary": self.summary,
            "architecture": list(self.architecture or []),
            "risks": list(self.risks or []),
            "design_doc_path": self.design_doc_path,
        }


@dataclass
class ImplementationStep:
    step_id: str
    title: str
    description: str
    file_writes: List[Dict[str, str]] = field(default_factory=list)
    test_pattern: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any], *, fallback_step_id: str) -> "ImplementationStep":
        payload = dict(payload or {})
        writes: List[Dict[str, str]] = []
        for item in payload.get("file_writes") or []:
            if isinstance(item, dict):
                path = str(item.get("path") or "").strip()
                if path:
                    writes.append(
                        {
                            "path": path,
                            "content": str(item.get("content") or ""),
                        }
                    )
        return cls(
            step_id=str(payload.get("step_id") or fallback_step_id).strip(),
            title=str(payload.get("title") or fallback_step_id.replace("_", " ")).strip(),
            description=str(payload.get("description") or "").strip(),
            file_writes=writes,
            test_pattern=str(payload.get("test_pattern") or "").strip() or None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "description": self.description,
            "file_writes": list(self.file_writes or []),
            "test_pattern": self.test_pattern,
        }


@dataclass
class ImplementationPlan:
    summary: str
    steps: List[ImplementationStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass
class ArchitectTask:
    task_id: str
    trace_id: str
    parent_handoff_id: str
    delegation_chain_id: str
    requirements: str
    design_context: DesignContext = field(default_factory=DesignContext)
    implementation_steps: List[ImplementationStep] = field(default_factory=list)
    design_doc_path: Optional[str] = None
    auto_delegate: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.design_context, DesignContext):
            self.design_context = DesignContext.from_payload(self.design_context or {})
        normalized_steps: List[ImplementationStep] = []
        for index, item in enumerate(self.implementation_steps or [], start=1):
            if isinstance(item, ImplementationStep):
                normalized_steps.append(item)
                continue
            if isinstance(item, dict):
                normalized_steps.append(
                    ImplementationStep.from_payload(item, fallback_step_id=f"step_{index}")
                )
        self.implementation_steps = normalized_steps
        self.design_doc_path = str(self.design_doc_path or "").strip() or None
        self.auto_delegate = bool(self.auto_delegate)

    @classmethod
    def from_task_context(cls, context: Dict[str, Any]) -> "ArchitectTask":
        payload = dict(context or {})
        implementation_steps = payload.get("implementation_steps") or []
        if not implementation_steps and payload.get("file_writes"):
            implementation_steps = [
                {
                    "step_id": "step_1",
                    "title": "implement planned changes",
                    "description": "apply planned file updates",
                    "file_writes": list(payload.get("file_writes") or []),
                    "test_pattern": payload.get("test_pattern"),
                }
            ]
        return cls(
            task_id=str(payload.get("task_id") or "").strip(),
            trace_id=str(payload.get("trace_id") or "").strip(),
            parent_handoff_id=str(payload.get("parent_handoff_id") or "").strip(),
            delegation_chain_id=str(payload.get("delegation_chain_id") or "").strip(),
            requirements=str(payload.get("instruction") or payload.get("requirements") or "").strip(),
            design_context=payload.get("design_context") or {},
            implementation_steps=implementation_steps,
            design_doc_path=payload.get("design_doc_path"),
            auto_delegate=payload.get("auto_delegate", True),
        )


@dataclass
class ArchitectResult:
    success: bool
    summary: str
    design: DesignDocument
    plan: ImplementationPlan
    delegated_subagent: Optional[Dict[str, Any]] = None
    design_files: List[str] = field(default_factory=list)
    error_code: Optional[str] = None
    error_detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "summary": self.summary,
            "design": self.design.to_dict(),
            "plan": self.plan.to_dict(),
            "delegated_subagent": dict(self.delegated_subagent or {}) or None,
            "design_files": list(self.design_files or []),
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }


class SubAgentArchitectError(RuntimeError):
    """Raised when architect execution fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SubAgentArchitect:
    """Design and architecture planning subagent."""

    def __init__(
        self,
        *,
        subagent_manager: Optional[SubAgentManager] = None,
        message_bus: Any = None,
        persistence: Any = None,
    ) -> None:
        self._subagent_manager = subagent_manager
        self._message_bus = message_bus
        self._persistence = persistence
        self._active_worktree_root: Optional[Path] = None
        self._active_task: Optional[ArchitectTask] = None

    async def execute(
        self,
        task: ArchitectTask,
        worktree_context: WorktreeContext,
        progress_callback: Optional[Callable] = None,
    ) -> ArchitectResult:
        self._active_task = task
        self._active_worktree_root = Path(worktree_context.path).resolve()
        if not self._active_worktree_root.exists():
            raise SubAgentArchitectError(
                "worktree_missing",
                f"worktree path does not exist: {self._active_worktree_root}",
            )

        await self._emit_progress(
            task=task,
            status="running",
            phase="subagent_architect_start",
            summary="subagent architect started",
            percent=10,
            progress_callback=progress_callback,
        )

        try:
            design = await self.create_design(task.requirements, task.design_context)
            design_files: List[str] = []
            if task.design_doc_path:
                await self._write_design_document(task.design_doc_path, design)
                design_files.append(task.design_doc_path)
                design.design_doc_path = task.design_doc_path

            await self._emit_progress(
                task=task,
                status="running",
                phase="subagent_architect_design",
                summary="design created",
                percent=40,
                progress_callback=progress_callback,
            )
            await self._checkpoint(task, "subagent_architect_design_created", design.to_dict())

            plan = await self.plan_implementation(design)
            await self._emit_progress(
                task=task,
                status="running",
                phase="subagent_architect_plan",
                summary="implementation plan created",
                percent=70,
                progress_callback=progress_callback,
            )
            await self._checkpoint(task, "subagent_architect_plan_created", plan.to_dict())

            delegated_subagent = None
            if task.auto_delegate and plan.steps:
                delegated_subagent = await self.delegate_to_coder(plan, self._subagent_manager)

            result = ArchitectResult(
                success=True,
                summary="architecture plan completed",
                design=design,
                plan=plan,
                delegated_subagent=delegated_subagent,
                design_files=design_files,
            )
            await self._checkpoint(task, "subagent_architect_completed", result.to_dict())
            await self._emit_progress(
                task=task,
                status="completed",
                phase="subagent_architect_completed",
                summary=result.summary,
                percent=100,
                progress_callback=progress_callback,
            )
            return result
        except Exception as exc:
            error_code = exc.code if isinstance(exc, SubAgentArchitectError) else "subagent_architect_execution_failed"
            await self._checkpoint(
                task,
                "subagent_architect_failed",
                {
                    "error_code": str(error_code),
                    "error_detail": str(exc),
                },
            )
            await self._emit_progress(
                task=task,
                status="failed",
                phase="subagent_architect_failed",
                summary=f"subagent architect failed: {exc}",
                percent=100,
                progress_callback=progress_callback,
            )
            if isinstance(exc, SubAgentArchitectError):
                raise
            raise SubAgentArchitectError(str(error_code), str(exc)) from exc
        finally:
            self._active_task = None
            self._active_worktree_root = None

    async def create_design(
        self,
        requirements: str,
        context: DesignContext,
    ) -> DesignDocument:
        """Create architecture/design from requirements."""
        requirement_text = str(requirements or "").strip()
        if not requirement_text:
            raise SubAgentArchitectError("requirements_required", "requirements are required")

        summary = context.scope or "planned change"
        architecture = [
            f"Requirements focus: {requirement_text}",
            f"Implementation scope: {summary}",
        ]
        if context.target_files:
            architecture.append(f"Target files: {', '.join(context.target_files)}")
        if context.constraints:
            architecture.append(f"Constraints: {', '.join(context.constraints)}")
        risks = list(context.assumptions or [])
        if context.constraints:
            risks.append("Preserve compatibility with existing runtime contracts")
        return DesignDocument(
            title="Subagent Architect Design",
            requirements=requirement_text,
            summary=f"design for {summary}",
            architecture=architecture,
            risks=risks,
        )

    async def plan_implementation(
        self,
        design: DesignDocument,
    ) -> ImplementationPlan:
        """Break design into implementable tasks."""
        task = self._active_task
        if task is None:
            raise SubAgentArchitectError("architect_task_missing", "architect task is not initialized")

        steps = list(task.implementation_steps or [])
        if not steps:
            raise SubAgentArchitectError(
                "implementation_steps_required",
                "implementation_steps or file_writes are required for delegated execution",
            )

        return ImplementationPlan(
            summary=f"implementation plan for {design.summary}",
            steps=steps,
        )

    async def delegate_to_coder(
        self,
        plan: ImplementationPlan,
        subagent_manager: SubAgentManager,
    ) -> Dict[str, Any]:
        """Spawn coder subagent with planned tasks."""
        if subagent_manager is None:
            raise SubAgentArchitectError("subagent_manager_required", "subagent manager is required")
        task = self._active_task
        root = self._active_worktree_root
        if task is None:
            raise SubAgentArchitectError("architect_task_missing", "architect task is not initialized")
        if root is None:
            raise SubAgentArchitectError("worktree_not_set", "worktree root is not initialized")
        if not plan.steps:
            raise SubAgentArchitectError("implementation_steps_required", "plan must include at least one step")

        step = plan.steps[0]
        spawn_result = await subagent_manager.spawn(
            "subagent_coder",
            {
                "parent_handoff_id": task.parent_handoff_id,
                "delegation_chain_id": task.delegation_chain_id,
                "task_id": task.task_id,
                "trace_id": task.trace_id,
                "conversation_id": "",
                "instruction": step.description or plan.summary,
                "file_writes": list(step.file_writes or []),
                "test_pattern": step.test_pattern,
                "planned_by": "subagent_architect",
            },
            worktree_path=str(root),
        )
        return {
            "agent_id": spawn_result.get("agent_id"),
            "agent_type": spawn_result.get("agent_type"),
            "status": spawn_result.get("status"),
            "step_id": step.step_id,
        }

    async def _write_design_document(self, path: str, design: DesignDocument) -> None:
        root = self._active_worktree_root
        if root is None:
            raise SubAgentArchitectError("worktree_not_set", "worktree root is not initialized")
        relative_path = str(path or "").strip()
        if not relative_path:
            raise SubAgentArchitectError("design_doc_path_required", "design_doc_path is required")
        target = (root / relative_path).resolve()
        if not self._is_within_root(target, root):
            raise SubAgentArchitectError("path_escape_denied", f"refusing to write outside worktree: {relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render_design_document(design), encoding="utf-8")

    @staticmethod
    def _render_design_document(design: DesignDocument) -> str:
        lines = [
            f"# {design.title}",
            "",
            "## Summary",
            design.summary,
            "",
            "## Requirements",
            design.requirements,
            "",
            "## Architecture",
        ]
        lines.extend(f"- {item}" for item in design.architecture)
        if design.risks:
            lines.extend(["", "## Risks"])
            lines.extend(f"- {item}" for item in design.risks)
        lines.append("")
        return "\n".join(lines)

    async def _emit_progress(
        self,
        *,
        task: ArchitectTask,
        status: str,
        phase: str,
        summary: str,
        percent: int,
        progress_callback: Optional[Callable],
    ) -> None:
        payload = {
            "phase": phase,
            "agent": "subagent_architect",
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

    async def _checkpoint(self, task: ArchitectTask, event: str, payload: Dict[str, Any]) -> None:
        save_checkpoint = getattr(self._persistence, "save_checkpoint", None)
        if not callable(save_checkpoint) or not task.task_id:
            return
        maybe = save_checkpoint(
            task_id=task.task_id,
            step_id="subagent_architect",
            payload={
                "event": event,
                "agent": "subagent_architect",
                "parent_handoff_id": task.parent_handoff_id,
                "delegation_chain_id": task.delegation_chain_id,
                "result": json.loads(json.dumps(payload, ensure_ascii=True)),
            },
        )
        if asyncio.iscoroutine(maybe):
            await maybe

    @staticmethod
    def _is_within_root(target: Path, root: Path) -> bool:
        target_s = str(target)
        root_s = str(root)
        if target_s == root_s:
            return True
        return target_s.startswith(root_s + "/")
