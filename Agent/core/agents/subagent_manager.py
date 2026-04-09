"""Phase 2 runtime lifecycle manager for delegated subagents."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)

SubAgentFailureHook = Callable[[str, str], Awaitable[None] | None]
SubAgentLifecycleFactory = Callable[[str, Dict[str, Any], Optional[str]], Awaitable[Any] | Any]

DEFAULT_SUBAGENT_TYPES = {
    "subagent_coder",
    "subagent_reviewer",
    "subagent_architect",
}
TERMINAL_STATES = {"terminated", "failed"}


class SubAgentLifecycleError(RuntimeError):
    """Raised when a subagent lifecycle operation fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class SubAgentRuntimeState:
    agent_id: str
    agent_type: str
    status: str
    task_context: Dict[str, Any]
    parent_handoff_id: str
    delegation_chain_id: str
    trace_id: str = ""
    task_id: str = ""
    conversation_id: str = ""
    worktree_path: Optional[str] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    created_at: float = field(default_factory=lambda: float(time.time()))
    updated_at: float = field(default_factory=lambda: float(time.time()))
    ended_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "status": self.status,
            "task_context": dict(self.task_context or {}),
            "parent_handoff_id": self.parent_handoff_id,
            "delegation_chain_id": self.delegation_chain_id,
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "conversation_id": self.conversation_id,
            "worktree_path": self.worktree_path,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ended_at": self.ended_at,
            "metadata": dict(self.metadata or {}),
        }


class SubAgentManager:
    """Deterministic lifecycle manager for spawned subagents."""

    def __init__(
        self,
        *,
        lifecycle_factory: Optional[SubAgentLifecycleFactory] = None,
        worktree_manager: Any = None,
        persistence: Any = None,
        message_bus: Any = None,
        failure_hook: Optional[SubAgentFailureHook] = None,
        allowed_agent_types: Optional[set[str]] = None,
    ) -> None:
        self._lifecycle_factory = lifecycle_factory
        self._worktree_manager = worktree_manager
        self._persistence = persistence
        self._message_bus = message_bus
        self._failure_hook = failure_hook
        self._allowed_agent_types = set(allowed_agent_types or DEFAULT_SUBAGENT_TYPES)
        self._states: Dict[str, SubAgentRuntimeState] = {}
        self._handles: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def spawn(
        self,
        agent_type: str,
        task_context: Dict[str, Any],
        worktree_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_type = str(agent_type or "").strip().lower()
        if normalized_type not in self._allowed_agent_types:
            raise SubAgentLifecycleError(
                "subagent_type_not_allowed",
                f"unsupported subagent type: {normalized_type}",
            )

        context = dict(task_context or {})
        parent_handoff_id = str(context.get("parent_handoff_id") or "").strip()
        delegation_chain_id = str(context.get("delegation_chain_id") or "").strip()
        if not parent_handoff_id or not delegation_chain_id:
            raise SubAgentLifecycleError(
                "subagent_lineage_required",
                "parent_handoff_id and delegation_chain_id are required",
            )

        agent_id = f"subag_{uuid.uuid4().hex[:12]}"
        state = SubAgentRuntimeState(
            agent_id=agent_id,
            agent_type=normalized_type,
            status="spawning",
            task_context=context,
            parent_handoff_id=parent_handoff_id,
            delegation_chain_id=delegation_chain_id,
            trace_id=str(context.get("trace_id") or "").strip(),
            task_id=str(context.get("task_id") or "").strip(),
            conversation_id=str(context.get("conversation_id") or "").strip(),
            worktree_path=worktree_path,
            metadata={
                "requested_worktree_path": worktree_path,
            },
        )

        async with self._lock:
            self._states[agent_id] = state

        try:
            if not state.worktree_path:
                worktree_info = await self._create_worktree(
                    agent_id=agent_id,
                    agent_type=normalized_type,
                    task_context=context,
                )
                state.worktree_path = str(worktree_info.get("path") or "").strip() or None
                worktree_id = str(worktree_info.get("worktree_id") or "").strip()
                if worktree_id:
                    state.metadata["worktree_id"] = worktree_id

            handle = await self._create_runtime_handle(
                agent_type=normalized_type,
                task_context=context,
                worktree_path=state.worktree_path,
            )
            if handle is not None:
                self._handles[agent_id] = handle

            state.status = "running"
            state.updated_at = float(time.time())

            await self._save_checkpoint(
                state=state,
                event="subagent_spawned",
                payload={
                    "agent_type": normalized_type,
                    "worktree_path": state.worktree_path,
                },
            )
            await self._emit_progress(
                state=state,
                status="running",
                phase="subagent_spawn",
                summary=f"{normalized_type} spawned",
                percent=5,
            )
            return state.to_dict()
        except Exception as exc:
            await self._mark_failed(
                state,
                error_code="subagent_spawn_failed",
                error_detail=str(exc),
            )
            raise

    async def terminate(self, agent_id: str) -> Dict[str, Any]:
        normalized_id = str(agent_id or "").strip()
        state = self._states.get(normalized_id)
        if state is None:
            raise LookupError(f"subagent_not_found:{normalized_id}")

        if state.status in TERMINAL_STATES:
            return state.to_dict()

        handle = self._handles.pop(normalized_id, None)
        if handle is not None:
            await self._terminate_handle(handle)

        await self._cleanup_worktree(state)
        state.status = "terminated"
        state.updated_at = float(time.time())
        state.ended_at = state.updated_at

        await self._save_checkpoint(
            state=state,
            event="subagent_terminated",
            payload={"agent_type": state.agent_type},
        )
        await self._emit_progress(
            state=state,
            status="cancelled",
            phase="subagent_terminate",
            summary=f"{state.agent_type} terminated",
            percent=100,
        )
        return state.to_dict()

    def get_status(self, agent_id: str) -> Dict[str, Any]:
        normalized_id = str(agent_id or "").strip()
        state = self._states.get(normalized_id)
        if state is None:
            raise LookupError(f"subagent_not_found:{normalized_id}")
        return state.to_dict()

    async def record_failure(self, agent_id: str, *, error_code: str, error_detail: str) -> Dict[str, Any]:
        normalized_id = str(agent_id or "").strip()
        state = self._states.get(normalized_id)
        if state is None:
            raise LookupError(f"subagent_not_found:{normalized_id}")
        await self._mark_failed(state, error_code=error_code, error_detail=error_detail)
        return state.to_dict()

    async def _create_runtime_handle(
        self,
        *,
        agent_type: str,
        task_context: Dict[str, Any],
        worktree_path: Optional[str],
    ) -> Any:
        if self._lifecycle_factory is None:
            return None
        maybe = self._lifecycle_factory(agent_type, task_context, worktree_path)
        if asyncio.iscoroutine(maybe):
            return await maybe
        return maybe

    async def _create_worktree(
        self,
        *,
        agent_id: str,
        agent_type: str,
        task_context: Dict[str, Any],
    ) -> Dict[str, Optional[str]]:
        manager = self._worktree_manager
        if manager is None:
            return {"path": None, "worktree_id": None}

        if hasattr(manager, "create_worktree"):
            try:
                maybe = manager.create_worktree(
                    agent_id=agent_id,
                    agent_type=agent_type,
                    task_context=task_context,
                )
            except TypeError:
                maybe = manager.create_worktree(
                    base_branch=str(task_context.get("base_branch") or "HEAD"),
                    task_id=str(task_context.get("task_id") or agent_id),
                    worktree_base=task_context.get("worktree_base"),
                )
        elif hasattr(manager, "create"):
            maybe = manager.create(
                agent_id=agent_id,
                agent_type=agent_type,
                task_context=task_context,
            )
        else:
            raise SubAgentLifecycleError(
                "worktree_manager_invalid",
                "worktree manager missing create/create_worktree",
            )

        if asyncio.iscoroutine(maybe):
            result = await maybe
        else:
            result = maybe

        if isinstance(result, str):
            return {"path": result, "worktree_id": None}
        if isinstance(result, dict):
            return {
                "path": str(result.get("path") or "").strip() or None,
                "worktree_id": str(result.get("worktree_id") or "").strip() or None,
            }

        worktree_path = str(getattr(result, "path", "") or "").strip() or None
        worktree_id = str(getattr(result, "worktree_id", "") or "").strip() or None
        return {"path": worktree_path, "worktree_id": worktree_id}

    async def _cleanup_worktree(self, state: SubAgentRuntimeState) -> None:
        if self._worktree_manager is None:
            return

        manager = self._worktree_manager
        worktree_id = str((state.metadata or {}).get("worktree_id") or "").strip()
        if worktree_id and hasattr(manager, "cleanup"):
            policy = "ON_FAILURE" if state.status == "failed" else "ON_SUCCESS"
            cleanup_policy = getattr(getattr(manager, "CleanupPolicy", None), policy, None)
            maybe = manager.cleanup(
                worktree_id=worktree_id,
                policy=cleanup_policy if cleanup_policy is not None else policy.lower(),
            )
            if asyncio.iscoroutine(maybe):
                await maybe
            return

        if not state.worktree_path:
            return

        if hasattr(manager, "cleanup_worktree"):
            maybe = manager.cleanup_worktree(
                worktree_path=state.worktree_path,
                status=state.status,
                agent_id=state.agent_id,
            )
        elif hasattr(manager, "cleanup"):
            maybe = manager.cleanup(
                worktree_path=state.worktree_path,
                status=state.status,
                agent_id=state.agent_id,
            )
        else:
            return

        if asyncio.iscoroutine(maybe):
            await maybe

    async def _terminate_handle(self, handle: Any) -> None:
        for method_name in ("terminate", "stop", "cancel"):
            method = getattr(handle, method_name, None)
            if callable(method):
                maybe = method()
                if asyncio.iscoroutine(maybe):
                    await maybe
                return
        if isinstance(handle, asyncio.Task) and not handle.done():
            handle.cancel()
            try:
                await handle
            except asyncio.CancelledError:
                return

    async def _save_checkpoint(
        self,
        *,
        state: SubAgentRuntimeState,
        event: str,
        payload: Dict[str, Any],
    ) -> None:
        if self._persistence is None or not state.task_id:
            return
        fn = getattr(self._persistence, "save_checkpoint", None)
        if not callable(fn):
            return
        maybe = fn(
            task_id=state.task_id,
            step_id=state.agent_id,
            payload={
                "event": event,
                "agent_id": state.agent_id,
                "agent_type": state.agent_type,
                "parent_handoff_id": state.parent_handoff_id,
                "delegation_chain_id": state.delegation_chain_id,
                **dict(payload or {}),
            },
        )
        if asyncio.iscoroutine(maybe):
            await maybe

    async def _emit_progress(
        self,
        *,
        state: SubAgentRuntimeState,
        status: str,
        phase: str,
        summary: str,
        percent: int,
    ) -> None:
        if self._message_bus is None:
            return
        publish = getattr(self._message_bus, "publish", None)
        if not callable(publish):
            return
        maybe = publish(
            "agent.progress",
            {
                "phase": phase,
                "agent": state.agent_type,
                "status": status,
                "percent": percent,
                "summary": summary,
                "session_id": state.conversation_id,
                "conversation_id": state.conversation_id,
                "parent_handoff_id": state.parent_handoff_id,
                "delegation_chain_id": state.delegation_chain_id,
            },
            trace_id=state.trace_id,
            handoff_id=state.parent_handoff_id,
            task_id=state.task_id,
            metadata={"agent_id": state.agent_id},
        )
        if asyncio.iscoroutine(maybe):
            await maybe

    async def _notify_failure(self, state: SubAgentRuntimeState) -> None:
        if self._failure_hook is None:
            return
        maybe = self._failure_hook(state.agent_type, state.agent_id)
        if asyncio.iscoroutine(maybe):
            await maybe

    async def _mark_failed(
        self,
        state: SubAgentRuntimeState,
        *,
        error_code: str,
        error_detail: str,
    ) -> None:
        state.status = "failed"
        state.error_code = str(error_code or "").strip() or "subagent_failed"
        state.error_detail = str(error_detail or "").strip()
        state.updated_at = float(time.time())
        state.ended_at = state.updated_at

        await self._cleanup_worktree(state)

        if self._persistence is not None and state.task_id:
            mark_terminal = getattr(self._persistence, "mark_terminal", None)
            if callable(mark_terminal):
                maybe = mark_terminal(
                    task_id=state.task_id,
                    status="FAILED",
                    reason=f"{state.error_code}:{state.error_detail}",
                )
                if asyncio.iscoroutine(maybe):
                    await maybe

        await self._emit_progress(
            state=state,
            status="failed",
            phase="subagent_failed",
            summary=f"{state.agent_type} failed",
            percent=100,
        )
        await self._notify_failure(state)
