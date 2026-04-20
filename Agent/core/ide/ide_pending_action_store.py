"""Pending action store with TTL eviction, idempotency, and audit logging."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PendingAction:
    """Action awaiting approval/execution."""

    action_id: str
    user_id: str
    session_id: str
    action_type: str
    target_id: str
    payload: Dict[str, Any]
    risk: str
    policy_reason: str
    idempotency_key: str
    requested_at: float
    expires_at: float
    trace_id: Optional[str] = None
    task_id: Optional[str] = None


@dataclass(slots=True)
class ActionAuditEvent:
    """Audit event for action lifecycle."""

    action_id: str
    event_type: str  # requested|approved|denied|executed|failed|cancelled|expired
    timestamp: float
    user_id: str
    session_id: str
    action_type: str
    risk: str
    idempotency_key: Optional[str] = None
    decided_by: Optional[str] = None
    decided_at: Optional[float] = None
    execution_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    trace_id: Optional[str] = None
    task_id: Optional[str] = None


class PendingActionStore:
    """In-memory pending action state with bounded audit history."""

    def __init__(
        self,
        *,
        max_actions: int = 1000,
        default_ttl_seconds: int = 600,
        cleanup_interval_seconds: int = 60,
        max_audit_events: int = 5000,
    ) -> None:
        self._max_actions = max(1, int(max_actions))
        self._default_ttl = max(1, int(default_ttl_seconds))
        self._cleanup_interval = max(1, int(cleanup_interval_seconds))
        self._max_audit_events = max(100, int(max_audit_events))

        self._actions: Dict[str, PendingAction] = {}
        self._idempotency_keys: Dict[str, str] = {}  # key -> action_id
        self._audit_events: Deque[ActionAuditEvent] = deque(maxlen=self._max_audit_events)

        self._cleanup_task: Optional[asyncio.Task[Any]] = None
        self._audit_callbacks: List[Callable[[ActionAuditEvent], Coroutine[Any, Any, None]]] = []
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("pending_action_store_started")

    async def stop(self) -> None:
        task = self._cleanup_task
        self._cleanup_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            self._actions.clear()
            self._idempotency_keys.clear()

        logger.info("pending_action_store_stopped")

    async def request(
        self,
        *,
        user_id: str,
        session_id: str,
        action_type: str,
        target_id: str,
        payload: Dict[str, Any],
        risk: str,
        policy_reason: str,
        idempotency_key: str,
        trace_id: Optional[str] = None,
        task_id: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> PendingAction:
        """Create or return idempotent pending action."""
        audit_event: Optional[ActionAuditEvent] = None

        async with self._lock:
            existing_id = self._idempotency_keys.get(idempotency_key)
            if existing_id:
                existing = self._actions.get(existing_id)
                if existing is not None:
                    logger.debug("pending_action_idempotency_hit key=%s action_id=%s", idempotency_key, existing_id)
                    return existing
                self._idempotency_keys.pop(idempotency_key, None)

            while len(self._actions) >= self._max_actions:
                oldest_id = next(iter(self._actions))
                evicted = self._pop_action_without_audit(oldest_id)
                if evicted is not None:
                    self._audit_events.append(
                        ActionAuditEvent(
                            action_id=evicted.action_id,
                            event_type="expired",
                            timestamp=time.monotonic(),
                            user_id=evicted.user_id,
                            session_id=evicted.session_id,
                            action_type=evicted.action_type,
                            risk=evicted.risk,
                            idempotency_key=evicted.idempotency_key,
                            error="evicted:capacity",
                            trace_id=evicted.trace_id,
                            task_id=evicted.task_id,
                        )
                    )

            action_id = f"act_{uuid.uuid4().hex[:16]}"
            now = time.monotonic()
            ttl = max(1, int(ttl_seconds or self._default_ttl))
            action = PendingAction(
                action_id=action_id,
                user_id=user_id,
                session_id=session_id,
                action_type=action_type,
                target_id=target_id,
                payload=dict(payload or {}),
                risk=risk,
                policy_reason=policy_reason,
                idempotency_key=idempotency_key,
                requested_at=now,
                expires_at=now + ttl,
                trace_id=trace_id,
                task_id=task_id,
            )
            self._actions[action_id] = action
            self._idempotency_keys[idempotency_key] = action_id

            audit_event = ActionAuditEvent(
                action_id=action_id,
                event_type="requested",
                timestamp=now,
                user_id=user_id,
                session_id=session_id,
                action_type=action_type,
                risk=risk,
                idempotency_key=idempotency_key,
                trace_id=trace_id,
                task_id=task_id,
            )
            self._audit_events.append(audit_event)

        if audit_event is not None:
            await self._notify_audit(audit_event)
        logger.info("pending_action_requested action_id=%s type=%s", action_id, action_type)
        return action

    async def get_pending(self, *, user_id: Optional[str] = None) -> List[PendingAction]:
        async with self._lock:
            actions = list(self._actions.values())
        if user_id:
            actions = [action for action in actions if action.user_id == user_id]
        return sorted(actions, key=lambda action: action.requested_at, reverse=True)

    async def get_by_id(self, action_id: str) -> Optional[PendingAction]:
        async with self._lock:
            return self._actions.get(action_id)

    async def approve(
        self,
        *,
        action_id: str,
        decided_by: str,
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> Optional[PendingAction]:
        audit_event: Optional[ActionAuditEvent] = None
        async with self._lock:
            action = self._pop_action_without_audit(action_id)
            if action is None:
                return None
            now = time.monotonic()
            audit_event = ActionAuditEvent(
                action_id=action_id,
                event_type="approved",
                timestamp=now,
                user_id=action.user_id,
                session_id=action.session_id,
                action_type=action.action_type,
                risk=action.risk,
                idempotency_key=action.idempotency_key,
                decided_by=decided_by,
                decided_at=now,
                execution_result=dict(execution_result or {}),
                trace_id=action.trace_id,
                task_id=action.task_id,
            )
            self._audit_events.append(audit_event)

        if audit_event is not None:
            await self._notify_audit(audit_event)
        logger.info("pending_action_approved action_id=%s decided_by=%s", action_id, decided_by)
        return action

    async def deny(
        self,
        *,
        action_id: str,
        decided_by: str,
        reason: str,
    ) -> bool:
        audit_event: Optional[ActionAuditEvent] = None
        async with self._lock:
            action = self._pop_action_without_audit(action_id)
            if action is None:
                return False
            now = time.monotonic()
            audit_event = ActionAuditEvent(
                action_id=action_id,
                event_type="denied",
                timestamp=now,
                user_id=action.user_id,
                session_id=action.session_id,
                action_type=action.action_type,
                risk=action.risk,
                idempotency_key=action.idempotency_key,
                decided_by=decided_by,
                decided_at=now,
                error=str(reason),
                trace_id=action.trace_id,
                task_id=action.task_id,
            )
            self._audit_events.append(audit_event)

        if audit_event is not None:
            await self._notify_audit(audit_event)
        logger.info("pending_action_denied action_id=%s decided_by=%s", action_id, decided_by)
        return True

    async def cancel(self, *, action_id: str, user_id: str) -> bool:
        audit_event: Optional[ActionAuditEvent] = None
        async with self._lock:
            action = self._actions.get(action_id)
            if action is None or action.user_id != user_id:
                return False
            action = self._pop_action_without_audit(action_id)
            if action is None:
                return False

            now = time.monotonic()
            audit_event = ActionAuditEvent(
                action_id=action_id,
                event_type="cancelled",
                timestamp=now,
                user_id=action.user_id,
                session_id=action.session_id,
                action_type=action.action_type,
                risk=action.risk,
                idempotency_key=action.idempotency_key,
                decided_by=user_id,
                decided_at=now,
                trace_id=action.trace_id,
                task_id=action.task_id,
            )
            self._audit_events.append(audit_event)

        if audit_event is not None:
            await self._notify_audit(audit_event)
        logger.info("pending_action_cancelled action_id=%s user_id=%s", action_id, user_id)
        return True

    async def record_execution_result(
        self,
        *,
        action: PendingAction,
        succeeded: bool,
        execution_result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        event_type = "executed" if succeeded else "failed"
        event = ActionAuditEvent(
            action_id=action.action_id,
            event_type=event_type,
            timestamp=time.monotonic(),
            user_id=action.user_id,
            session_id=action.session_id,
            action_type=action.action_type,
            risk=action.risk,
            idempotency_key=action.idempotency_key,
            execution_result=dict(execution_result or {}),
            error=str(error or "") or None,
            trace_id=action.trace_id,
            task_id=action.task_id,
        )
        async with self._lock:
            self._audit_events.append(event)
        await self._notify_audit(event)

    async def get_audit_events(
        self,
        *,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[ActionAuditEvent]:
        normalized_limit = max(1, min(int(limit or 200), self._max_audit_events))
        async with self._lock:
            events = list(self._audit_events)

        if user_id:
            events = [event for event in events if event.user_id == user_id]
        if session_id:
            events = [event for event in events if event.session_id == session_id]

        events.sort(key=lambda event: event.timestamp, reverse=True)
        return events[:normalized_limit]

    async def is_action_pending(self, action_type: str, target_id: str) -> bool:
        async with self._lock:
            return any(
                action.action_type == action_type and action.target_id == target_id
                for action in self._actions.values()
            )

    def on_audit(self, callback: Callable[[ActionAuditEvent], Coroutine[Any, Any, None]]) -> None:
        self._audit_callbacks.append(callback)

    async def _notify_audit(self, event: ActionAuditEvent) -> None:
        for callback in list(self._audit_callbacks):
            try:
                await callback(event)
            except Exception as exc:  # pragma: no cover - defensive callback handling
                logger.warning("pending_action_audit_callback_failed error=%s", exc)

    def _pop_action_without_audit(self, action_id: str) -> Optional[PendingAction]:
        action = self._actions.pop(action_id, None)
        if action is not None:
            self._idempotency_keys.pop(action.idempotency_key, None)
        return action

    async def _cleanup_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval)
                now = time.monotonic()
                expired: List[PendingAction] = []
                async with self._lock:
                    expired_ids = [
                        action_id
                        for action_id, action in self._actions.items()
                        if now > action.expires_at
                    ]
                    for action_id in expired_ids:
                        action = self._pop_action_without_audit(action_id)
                        if action is None:
                            continue
                        expired.append(action)
                        self._audit_events.append(
                            ActionAuditEvent(
                                action_id=action.action_id,
                                event_type="expired",
                                timestamp=now,
                                user_id=action.user_id,
                                session_id=action.session_id,
                                action_type=action.action_type,
                                risk=action.risk,
                                idempotency_key=action.idempotency_key,
                                error="evicted:expired",
                                trace_id=action.trace_id,
                                task_id=action.task_id,
                            )
                        )

                for action in expired:
                    await self._notify_audit(
                        ActionAuditEvent(
                            action_id=action.action_id,
                            event_type="expired",
                            timestamp=now,
                            user_id=action.user_id,
                            session_id=action.session_id,
                            action_type=action.action_type,
                            risk=action.risk,
                            idempotency_key=action.idempotency_key,
                            error="evicted:expired",
                            trace_id=action.trace_id,
                            task_id=action.task_id,
                        )
                    )
        except asyncio.CancelledError:
            return
