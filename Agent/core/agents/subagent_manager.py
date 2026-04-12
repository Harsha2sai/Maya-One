"""Phase 2 runtime lifecycle manager for delegated subagents."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

from config.settings import settings
from core.agents.subagent_persistence_bridge import RecoveryPolicy, SubagentPersistenceBridge
from core.messaging.progress_stream import ProgressStream

logger = logging.getLogger(__name__)

SubAgentFailureHook = Callable[[str, str], Awaitable[None] | None]
SubAgentLifecycleFactory = Callable[[str, Dict[str, Any], Optional[str]], Awaitable[Any] | Any]

DEFAULT_SUBAGENT_TYPES = {
    "subagent_coder",
    "subagent_reviewer",
    "subagent_architect",
}
TERMINAL_STATES = {"terminated", "failed", "completed"}


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


@dataclass
class BackgroundTaskState:
    task_ref: str
    agent_id: str
    agent_type: str
    status: str
    task_id: str = ""
    trace_id: str = ""
    worktree_path: Optional[str] = None
    recoverable: bool = False
    created_at: float = field(default_factory=lambda: float(time.time()))
    updated_at: float = field(default_factory=lambda: float(time.time()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_ref": self.task_ref,
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "status": self.status,
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "worktree_path": self.worktree_path,
            "recoverable": self.recoverable,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
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
        progress_stream: Optional[ProgressStream] = None,
        failure_hook: Optional[SubAgentFailureHook] = None,
        persistence_bridge: Optional[SubagentPersistenceBridge] = None,
        allowed_agent_types: Optional[set[str]] = None,
    ) -> None:
        self._lifecycle_factory = lifecycle_factory
        self._worktree_manager = worktree_manager
        self._persistence = persistence
        self._message_bus = message_bus
        self._progress_stream = progress_stream or (
            ProgressStream(
                message_bus=message_bus,
                max_events_per_sec=int(getattr(settings, "max_progress_events_per_sec_per_session", 10)),
            )
            if message_bus is not None
            else None
        )
        self._failure_hook = failure_hook
        self._allowed_agent_types = set(allowed_agent_types or DEFAULT_SUBAGENT_TYPES)
        self._states: Dict[str, SubAgentRuntimeState] = {}
        self._background_tasks: Dict[str, BackgroundTaskState] = {}
        self._handles: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._persistence_bridge = persistence_bridge or SubagentPersistenceBridge(
            persistence=self._persistence,
            subagent_manager=self,
        )

    async def spawn(
        self,
        agent_type: str,
        task_context: Dict[str, Any],
        worktree_path: Optional[str] = None,
        wait: bool = True,
        recoverable: bool = False,
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

        requested_agent_id = str(context.get("agent_id") or "").strip()
        agent_id = requested_agent_id or f"subag_{uuid.uuid4().hex[:12]}"
        existing_state = self._states.get(agent_id)
        if existing_state is not None and existing_state.status not in TERMINAL_STATES:
            raise SubAgentLifecycleError(
                "subagent_id_conflict",
                f"subagent id already active: {agent_id}",
            )
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
                "recoverable": bool(recoverable),
                "background": not wait,
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
                if isinstance(handle, asyncio.Task):
                    self._attach_task_monitor(agent_id, handle)

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
            if recoverable and self._persistence_bridge is not None:
                await self._persistence_bridge.mark_recoverable(agent_id, RecoveryPolicy.ALWAYS)
            await self._persist_recovery_state(state)

            if wait:
                return state.to_dict()

            background = self._register_background_task(state)
            return background.to_dict()
        except Exception as exc:
            await self._mark_failed(
                state,
                error_code="subagent_spawn_failed",
                error_detail=str(exc),
            )
            raise

    async def spawn_background(
        self,
        agent_type: str,
        task_context: Dict[str, Any],
        recoverable: bool = True,
    ) -> Dict[str, Any]:
        return await self.spawn(
            agent_type,
            task_context,
            wait=False,
            recoverable=recoverable,
        )

    async def get_background_status(self, task_ref: str) -> Dict[str, Any]:
        normalized_ref = str(task_ref or "").strip()
        if not normalized_ref:
            raise LookupError("background_task_not_found:")

        background = self._background_tasks.get(normalized_ref)
        state = self._states.get(normalized_ref)
        if state is not None:
            if background is None:
                background = self._register_background_task(state)
            background.status = state.status
            background.updated_at = float(time.time())
            background.worktree_path = state.worktree_path
            return {
                **background.to_dict(),
                "error_code": state.error_code,
                "error_detail": state.error_detail,
                "result": dict(state.metadata or {}).get("result"),
            }

        if background is not None:
            return background.to_dict()

        if self._persistence_bridge is not None:
            snapshot = await self._persistence_bridge.get_snapshot(normalized_ref)
            if snapshot is not None:
                state_payload = dict(snapshot.get("state") or {})
                return {
                    "task_ref": normalized_ref,
                    "agent_id": normalized_ref,
                    "agent_type": state_payload.get("agent_type"),
                    "status": state_payload.get("status"),
                    "task_id": state_payload.get("task_id"),
                    "trace_id": state_payload.get("trace_id"),
                    "worktree_path": state_payload.get("worktree_path"),
                    "recoverable": snapshot.get("recovery_policy") != RecoveryPolicy.NEVER.value,
                    "created_at": state_payload.get("created_at"),
                    "updated_at": snapshot.get("updated_at"),
                    "error_code": state_payload.get("error_code"),
                    "error_detail": state_payload.get("error_detail"),
                    "result": dict(state_payload.get("metadata") or {}).get("result"),
                    "recovered_snapshot": True,
                }

        raise LookupError(f"background_task_not_found:{normalized_ref}")

    async def resume_background(self, task_ref: str) -> Dict[str, Any]:
        normalized_ref = str(task_ref or "").strip()
        if not normalized_ref:
            raise LookupError("background_task_not_found:")
        if self._persistence_bridge is None:
            raise SubAgentLifecycleError(
                "subagent_recovery_unavailable",
                "persistence bridge is not configured",
            )

        resumed = await self._persistence_bridge.resume_from_checkpoint(normalized_ref)
        if resumed is None:
            raise LookupError(f"background_checkpoint_not_found:{normalized_ref}")

        state = self._states.get(str(resumed.get("agent_id") or "").strip())
        if state is not None:
            self._register_background_task(state)
        return resumed

    async def await_completion(self, task_ref: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        normalized_ref = str(task_ref or "").strip()
        deadline = None if timeout is None else float(time.time()) + float(timeout)
        while True:
            status = await self.get_background_status(normalized_ref)
            if str(status.get("status") or "").strip().lower() in TERMINAL_STATES:
                return status
            if deadline is not None and float(time.time()) >= deadline:
                raise TimeoutError(f"background_task_timeout:{normalized_ref}")
            await asyncio.sleep(0.02)

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
        await self._persist_recovery_state(state)
        self._sync_background_state(state)
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

    def _attach_task_monitor(self, agent_id: str, task: asyncio.Task) -> None:
        def _done(done_task: asyncio.Task) -> None:
            asyncio.create_task(self._handle_task_done(agent_id, done_task))

        task.add_done_callback(_done)

    async def _handle_task_done(self, agent_id: str, task: asyncio.Task) -> None:
        state = self._states.get(agent_id)
        if state is None or state.status in TERMINAL_STATES:
            return
        self._handles.pop(agent_id, None)

        if task.cancelled():
            await self._mark_failed(
                state,
                error_code="subagent_task_cancelled",
                error_detail="runtime task cancelled",
            )
            return

        try:
            result = task.result()
        except Exception as exc:
            await self._mark_failed(
                state,
                error_code="subagent_runtime_failed",
                error_detail=str(exc),
            )
            return

        await self._mark_completed(state, result=result)

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
        progress_stream = self._progress_stream
        if progress_stream is None:
            return
        maybe = progress_stream.emit_progress(
            task_id=state.task_id,
            session_id=state.conversation_id,
            conversation_id=state.conversation_id,
            parent_handoff_id=state.parent_handoff_id,
            delegation_chain_id=state.delegation_chain_id,
            phase=phase,
            agent=state.agent_type,
            status=status,
            percent=percent,
            summary=summary,
            trace_id=state.trace_id,
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
        await self._persist_recovery_state(state)
        self._sync_background_state(state)
        await self._notify_failure(state)

    async def _mark_completed(self, state: SubAgentRuntimeState, *, result: Any) -> None:
        if state.status in TERMINAL_STATES:
            return

        state.status = "completed"
        state.updated_at = float(time.time())
        state.ended_at = state.updated_at
        state.metadata["result"] = self._to_jsonable(result)

        await self._save_checkpoint(
            state=state,
            event="subagent_completed",
            payload={"result": self._to_jsonable(result)},
        )

        if self._persistence is not None and state.task_id:
            mark_terminal = getattr(self._persistence, "mark_terminal", None)
            if callable(mark_terminal):
                maybe = mark_terminal(
                    task_id=state.task_id,
                    status="COMPLETED",
                    reason="subagent_completed",
                )
                if asyncio.iscoroutine(maybe):
                    await maybe

        await self._emit_progress(
            state=state,
            status="completed",
            phase="subagent_completed",
            summary=f"{state.agent_type} completed",
            percent=100,
        )
        await self._persist_recovery_state(state)
        self._sync_background_state(state)
        await self._cleanup_worktree(state)

    def _register_background_task(self, state: SubAgentRuntimeState) -> BackgroundTaskState:
        background = self._background_tasks.get(state.agent_id)
        if background is None:
            background = BackgroundTaskState(
                task_ref=state.agent_id,
                agent_id=state.agent_id,
                agent_type=state.agent_type,
                status=state.status,
                task_id=state.task_id,
                trace_id=state.trace_id,
                worktree_path=state.worktree_path,
                recoverable=bool((state.metadata or {}).get("recoverable")),
                created_at=state.created_at,
                updated_at=state.updated_at,
            )
            self._background_tasks[state.agent_id] = background
            return background

        background.status = state.status
        background.updated_at = state.updated_at
        background.worktree_path = state.worktree_path
        background.recoverable = bool((state.metadata or {}).get("recoverable"))
        return background

    def _sync_background_state(self, state: SubAgentRuntimeState) -> None:
        background = self._background_tasks.get(state.agent_id)
        if background is None:
            return
        background.status = state.status
        background.updated_at = state.updated_at
        background.worktree_path = state.worktree_path
        background.recoverable = bool((state.metadata or {}).get("recoverable"))

    async def _persist_recovery_state(self, state: SubAgentRuntimeState) -> None:
        bridge = self._persistence_bridge
        if bridge is None:
            return
        if not bool((state.metadata or {}).get("recoverable")):
            return
        await bridge.save_checkpoint(state.agent_id, state.to_dict())

    @staticmethod
    def _to_jsonable(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): SubAgentManager._to_jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [SubAgentManager._to_jsonable(v) for v in value]
        if hasattr(value, "to_dict") and callable(value.to_dict):
            try:
                return SubAgentManager._to_jsonable(value.to_dict())
            except Exception:
                return str(value)
        if hasattr(value, "__dict__"):
            try:
                return SubAgentManager._to_jsonable(dict(value.__dict__))
            except Exception:
                return str(value)
        return str(value)
