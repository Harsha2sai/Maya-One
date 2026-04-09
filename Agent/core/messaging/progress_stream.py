"""Bridge bus progress events to existing client event path with throttling."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from config.settings import settings
from core.messaging.message_bus import MessageBus, MessageEnvelope
from core.telemetry.runtime_metrics import RuntimeMetrics

logger = logging.getLogger(__name__)

TERMINAL_PROGRESS_STATUSES = {"completed", "failed", "cancelled"}


@dataclass
class _RateBucket:
    ts_window: deque[float]


class ProgressStream:
    """Progress bridge with per-session event-rate controls."""

    def __init__(
        self,
        *,
        bus: MessageBus,
        emitter: Callable[[Dict[str, Any]], Awaitable[None] | None],
        max_events_per_sec_per_session: Optional[int] = None,
    ) -> None:
        self._bus = bus
        self._emitter = emitter
        self._max_rate = int(
            max_events_per_sec_per_session
            if max_events_per_sec_per_session is not None
            else getattr(settings, "max_progress_events_per_sec_per_session", 10)
        )
        self._session_buckets: Dict[str, _RateBucket] = {}
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self._bus.subscribe("agent.progress", self._on_progress_event)
        self._started = True
        logger.info("progress_stream_started max_events_per_sec_per_session=%s", self._max_rate)

    async def stop(self) -> None:
        if not self._started:
            return
        await self._bus.unsubscribe("agent.progress", self._on_progress_event)
        self._started = False
        logger.info("progress_stream_stopped")

    async def _on_progress_event(self, envelope: MessageEnvelope) -> None:
        payload = dict(envelope.payload or {})
        status = str(payload.get("status") or "").strip().lower()
        session_id = (
            str(payload.get("session_id") or "").strip()
            or str(payload.get("conversation_id") or "").strip()
            or "unknown_session"
        )
        if status not in TERMINAL_PROGRESS_STATUSES and not self._allow_emit(session_id):
            logger.info(
                "progress_event_throttled session_id=%s trace_id=%s task_id=%s",
                session_id,
                envelope.trace_id,
                envelope.task_id,
            )
            return

        normalized = {
            "phase": str(payload.get("phase") or "").strip(),
            "agent": str(payload.get("agent") or "").strip(),
            "status": status,
            "percent": payload.get("percent"),
            "summary": str(payload.get("summary") or "").strip(),
            "trace_id": envelope.trace_id,
            "task_id": envelope.task_id,
            "timestamp": envelope.timestamp,
            "message_id": envelope.message_id,
            "handoff_id": envelope.handoff_id,
        }
        try:
            maybe = self._emitter(normalized)
            if asyncio.iscoroutine(maybe):
                await maybe
            RuntimeMetrics.observe("progress_event_rate", 1.0)
        except Exception as err:
            logger.warning(
                "progress_stream_emit_failed trace_id=%s task_id=%s error=%s",
                envelope.trace_id,
                envelope.task_id,
                err,
            )

    def _allow_emit(self, session_id: str) -> bool:
        now = time.monotonic()
        bucket = self._session_buckets.get(session_id)
        if bucket is None:
            bucket = _RateBucket(ts_window=deque())
            self._session_buckets[session_id] = bucket

        while bucket.ts_window and (now - bucket.ts_window[0]) > 1.0:
            bucket.ts_window.popleft()
        if len(bucket.ts_window) >= max(1, self._max_rate):
            return False
        bucket.ts_window.append(now)
        return True
