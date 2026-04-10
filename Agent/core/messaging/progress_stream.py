"""Progress event bridge with throttling and terminal-state bypass."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional


class ProgressStream:
    TERMINAL_STATUSES = {"completed", "failed", "cancelled", "terminated"}

    def __init__(self, *, message_bus: Any, max_events_per_sec: int = 10, clock=None) -> None:
        self._message_bus = message_bus
        self._max_events_per_sec = max(1, int(max_events_per_sec or 10))
        self._clock = clock or time.monotonic
        self._last_event_at: Dict[str, float] = {}

    def _throttle_key(self, *, session_id: str, task_id: str, agent: str, phase: str) -> str:
        return f"{session_id}:{task_id}:{agent}:{phase}"

    def _should_emit(self, *, key: str, status: str) -> bool:
        normalized_status = str(status or "").strip().lower()
        if normalized_status in self.TERMINAL_STATUSES:
            return True

        now = float(self._clock())
        min_interval = 1.0 / float(self._max_events_per_sec)
        previous = self._last_event_at.get(key)
        if previous is not None and (now - previous) < min_interval:
            return False
        self._last_event_at[key] = now
        return True

    async def emit_progress(
        self,
        *,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        parent_handoff_id: Optional[str] = None,
        delegation_chain_id: Optional[str] = None,
        phase: Optional[str] = None,
        agent: Optional[str] = None,
        status: str = "running",
        percent: int = 0,
        summary: str = "",
        trace_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if self._message_bus is None:
            return None

        resolved_session_id = str(session_id or conversation_id or "").strip()
        resolved_task_id = str(task_id or "").strip()
        resolved_agent = str(agent or "").strip() or "unknown"
        resolved_phase = str(phase or "").strip() or "progress"
        key = self._throttle_key(
            session_id=resolved_session_id,
            task_id=resolved_task_id,
            agent=resolved_agent,
            phase=resolved_phase,
        )

        if not self._should_emit(key=key, status=status):
            return None

        payload = {
            "phase": resolved_phase,
            "agent": resolved_agent,
            "status": str(status or "").strip().lower() or "running",
            "percent": int(percent),
            "summary": str(summary or "").strip(),
            "session_id": resolved_session_id,
            "conversation_id": str(conversation_id or "").strip() or resolved_session_id,
            "parent_handoff_id": str(parent_handoff_id or "").strip() or None,
            "delegation_chain_id": str(delegation_chain_id or "").strip() or None,
        }

        return await self._message_bus.publish(
            "agent.progress",
            payload,
            trace_id=str(trace_id or "").strip() or None,
            handoff_id=str(parent_handoff_id or "").strip() or None,
            task_id=resolved_task_id or None,
            metadata=dict(metadata or {}),
        )

    async def stream_to_room(self, room_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self._message_bus is None:
            return None
        return await self._message_bus.publish(
            f"agent.progress.room.{str(room_id or '').strip()}",
            dict(payload or {}),
        )
