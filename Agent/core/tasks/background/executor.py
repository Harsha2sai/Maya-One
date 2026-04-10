"""Background task executor with checkpointing and crash-recovery hooks."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

TaskHandler = Callable[[Dict[str, Any]], Awaitable[Any] | Any]
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


@dataclass
class BackgroundTaskHandle:
    task_ref: str
    task_id: str
    task_type: str
    status: str
    payload: Dict[str, Any] = field(default_factory=dict)
    recoverable: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=lambda: float(time.time()))
    updated_at: float = field(default_factory=lambda: float(time.time()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_ref": self.task_ref,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status,
            "payload": dict(self.payload or {}),
            "recoverable": bool(self.recoverable),
            "metadata": dict(self.metadata or {}),
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class BackgroundExecutor:
    """Runs detached background work and persists lifecycle checkpoints."""

    def __init__(self, *, persistence: Any = None) -> None:
        self._persistence = persistence
        self._handlers: Dict[str, TaskHandler] = {}
        self._handles: Dict[str, BackgroundTaskHandle] = {}
        self._runtime_tasks: Dict[str, asyncio.Task[Any]] = {}
        self._lock = asyncio.Lock()

    def register_handler(self, task_type: str, handler: TaskHandler) -> None:
        normalized = str(task_type or "").strip().lower()
        if not normalized:
            raise ValueError("task_type is required")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._handlers[normalized] = handler

    def unregister_handler(self, task_type: str) -> None:
        normalized = str(task_type or "").strip().lower()
        self._handlers.pop(normalized, None)

    def has_handler(self, task_type: str) -> bool:
        normalized = str(task_type or "").strip().lower()
        return normalized in self._handlers

    async def submit(
        self,
        *,
        task_id: str,
        task_type: str,
        payload: Optional[Dict[str, Any]] = None,
        task_ref: Optional[str] = None,
        recoverable: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            raise ValueError("task_id is required")

        normalized_type = str(task_type or "").strip().lower()
        if normalized_type not in self._handlers:
            raise KeyError(f"unknown_task_type:{normalized_type}")

        resolved_ref = str(task_ref or f"bg_{uuid.uuid4().hex[:16]}")
        async with self._lock:
            existing = self._handles.get(resolved_ref)
            if existing is not None and existing.status not in TERMINAL_STATUSES:
                raise RuntimeError(f"background_task_already_running:{resolved_ref}")

            handle = BackgroundTaskHandle(
                task_ref=resolved_ref,
                task_id=normalized_task_id,
                task_type=normalized_type,
                status="running",
                payload=dict(payload or {}),
                recoverable=bool(recoverable),
                metadata=dict(metadata or {}),
            )
            self._handles[resolved_ref] = handle

        await self._save_checkpoint(
            handle,
            event="background_submitted",
            payload={
                "payload": dict(payload or {}),
                "metadata": dict(metadata or {}),
                "recoverable": bool(recoverable),
            },
        )

        runtime_task = asyncio.create_task(self._run_handle(handle))
        self._runtime_tasks[resolved_ref] = runtime_task
        return handle.to_dict()

    async def resume_task(self, recovered: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        metadata = dict((recovered or {}).get("metadata") or {})
        task_id = str((recovered or {}).get("task_id") or "").strip()
        if not task_id:
            return None

        status = str((recovered or {}).get("status") or "").strip().upper()
        if status in {"COMPLETED", "FAILED", "CANCELLED", "STALE", "PLAN_FAILED"}:
            return None

        task_type = str(
            metadata.get("task_type")
            or (recovered or {}).get("task_type")
            or metadata.get("background_task_type")
            or ""
        ).strip().lower()
        if not task_type:
            return None

        payload = metadata.get("payload") if isinstance(metadata.get("payload"), dict) else {}
        task_ref = str((recovered or {}).get("task_ref") or task_id)
        return await self.submit(
            task_id=task_id,
            task_type=task_type,
            payload=dict(payload),
            task_ref=task_ref,
            recoverable=bool(metadata.get("recoverable", True)),
            metadata=metadata,
        )

    async def get_status(self, task_ref: str) -> Dict[str, Any]:
        normalized = str(task_ref or "").strip()
        if not normalized or normalized not in self._handles:
            raise LookupError(f"background_task_not_found:{normalized}")
        return self._handles[normalized].to_dict()

    async def await_completion(self, task_ref: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        normalized = str(task_ref or "").strip()
        if not normalized:
            raise LookupError("background_task_not_found:")

        runtime = self._runtime_tasks.get(normalized)
        if runtime is None:
            status = await self.get_status(normalized)
            if status["status"] in TERMINAL_STATUSES:
                return status
            raise LookupError(f"background_runtime_not_found:{normalized}")

        try:
            await asyncio.wait_for(asyncio.shield(runtime), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"background_task_timeout:{normalized}") from None

        return await self.get_status(normalized)

    async def cancel(self, task_ref: str) -> Dict[str, Any]:
        normalized = str(task_ref or "").strip()
        if not normalized:
            raise LookupError("background_task_not_found:")

        runtime = self._runtime_tasks.get(normalized)
        if runtime is not None and not runtime.done():
            runtime.cancel()

        if normalized in self._handles:
            # Ensure state updates even when runtime already ended.
            handle = self._handles[normalized]
            if handle.status not in TERMINAL_STATUSES:
                await self._mark_cancelled(handle)
            return handle.to_dict()

        raise LookupError(f"background_task_not_found:{normalized}")

    async def shutdown(self, *, cancel_running: bool = True) -> None:
        refs = list(self._runtime_tasks.keys())
        for task_ref in refs:
            runtime = self._runtime_tasks.get(task_ref)
            if runtime is None:
                continue
            if cancel_running and not runtime.done():
                runtime.cancel()
                handle = self._handles.get(task_ref)
                if handle is not None and handle.status not in TERMINAL_STATUSES:
                    await self._mark_cancelled(handle)

        if refs:
            await asyncio.gather(*[t for t in self._runtime_tasks.values()], return_exceptions=True)

    async def _run_handle(self, handle: BackgroundTaskHandle) -> None:
        handler = self._handlers[handle.task_type]

        try:
            maybe = handler(dict(handle.payload or {}))
            result = await maybe if asyncio.iscoroutine(maybe) else maybe
            await self._mark_completed(handle, result)
        except asyncio.CancelledError:
            await self._mark_cancelled(handle)
            raise
        except Exception as exc:  # pragma: no cover - depends on handler behavior
            await self._mark_failed(handle, str(exc))
        finally:
            self._runtime_tasks.pop(handle.task_ref, None)

    async def _mark_completed(self, handle: BackgroundTaskHandle, result: Any) -> None:
        handle.status = "completed"
        handle.result = result
        handle.error = None
        handle.updated_at = float(time.time())
        await self._save_checkpoint(
            handle,
            event="background_completed",
            payload={"result": result},
        )
        await self._mark_terminal(handle, status="COMPLETED", reason="")

    async def _mark_failed(self, handle: BackgroundTaskHandle, error: str) -> None:
        handle.status = "failed"
        handle.error = str(error or "background_task_failed")
        handle.updated_at = float(time.time())
        await self._save_checkpoint(
            handle,
            event="background_failed",
            payload={"error": handle.error},
        )
        await self._mark_terminal(handle, status="FAILED", reason=handle.error)

    async def _mark_cancelled(self, handle: BackgroundTaskHandle) -> None:
        handle.status = "cancelled"
        handle.error = "task_cancelled"
        handle.updated_at = float(time.time())
        await self._save_checkpoint(
            handle,
            event="background_cancelled",
            payload={"reason": handle.error},
        )
        await self._mark_terminal(handle, status="CANCELLED", reason=handle.error)

    async def _save_checkpoint(self, handle: BackgroundTaskHandle, *, event: str, payload: Dict[str, Any]) -> None:
        if self._persistence is None:
            return

        save_checkpoint = getattr(self._persistence, "save_checkpoint", None)
        if not callable(save_checkpoint):
            return

        checkpoint_payload = {
            "event": event,
            "task_ref": handle.task_ref,
            "task_type": handle.task_type,
            "task_id": handle.task_id,
            "status": handle.status,
            "payload": payload,
            "metadata": dict(handle.metadata or {}),
            "recoverable": bool(handle.recoverable),
            "updated_at": handle.updated_at,
        }
        maybe = save_checkpoint(
            task_id=handle.task_id,
            step_id=handle.task_ref,
            payload=checkpoint_payload,
        )
        if asyncio.iscoroutine(maybe):
            await maybe

    async def _mark_terminal(self, handle: BackgroundTaskHandle, *, status: str, reason: str) -> None:
        if self._persistence is None:
            return

        mark_terminal = getattr(self._persistence, "mark_terminal", None)
        if not callable(mark_terminal):
            return

        maybe = mark_terminal(handle.task_id, status, reason)
        if asyncio.iscoroutine(maybe):
            await maybe
