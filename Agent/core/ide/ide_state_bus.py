from __future__ import annotations

import asyncio
import inspect
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any


IDEEventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class IDEStateBus:
    def __init__(
        self,
        queue_size: int = 200,
        replay_size: int = 10_000,
    ) -> None:
        self._queue_size = max(1, int(queue_size))
        self._replay_size = max(1, int(replay_size))
        self._queues: list[asyncio.Queue[dict[str, Any]]] = []
        self._queue_filters: dict[asyncio.Queue[dict[str, Any]], dict[str, Any]] = {}
        self._handlers: list[IDEEventHandler] = []
        self._event_buffer: deque[dict[str, Any]] = deque(maxlen=self._replay_size)
        self._seq = 0
        self._lock = asyncio.Lock()

    async def emit(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_payload = self._normalize_payload(payload)

        async with self._lock:
            self._seq += 1
            event = {
                "seq": self._seq,
                "event_type": str(event_type),
                "timestamp": float(normalized_payload.pop("timestamp", time.time())),
                "session_id": normalized_payload.pop("session_id", None),
                "trace_id": normalized_payload.pop("trace_id", None),
                "task_id": normalized_payload.pop("task_id", None),
                "agent_id": normalized_payload.pop("agent_id", None),
                "status": normalized_payload.pop("status", None),
                "payload": normalized_payload,
            }
            self._event_buffer.append(event)

            for queue in list(self._queues):
                if not self._matches_filters(event, self._queue_filters.get(queue) or {}):
                    continue
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    _ = queue.get_nowait()
                    queue.put_nowait(event)

        for handler in list(self._handlers):
            result = handler(event)
            if inspect.isawaitable(result):
                await result

        return event

    def subscribe(
        self,
        handler: IDEEventHandler | None = None,
        *,
        session_id: str | None = None,
        event_types: set[str] | None = None,
    ) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        self._queues.append(queue)
        self._queue_filters[queue] = {
            "session_id": str(session_id or "").strip() or None,
            "event_types": set(event_types or set()) or None,
        }
        if handler is not None:
            self._handlers.append(handler)
        return queue

    def unsubscribe(
        self,
        queue: asyncio.Queue[dict[str, Any]] | None = None,
        handler: IDEEventHandler | None = None,
    ) -> None:
        if queue is not None and queue in self._queues:
            self._queues.remove(queue)
            self._queue_filters.pop(queue, None)
        if handler is not None and handler in self._handlers:
            self._handlers.remove(handler)

    def get_events_since(
        self,
        *,
        after_seq: int = 0,
        limit: int = 500,
        session_id: str | None = None,
        event_types: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        normalized_after = max(0, int(after_seq))
        normalized_limit = max(1, min(int(limit or 500), self._replay_size))
        filters = {
            "session_id": str(session_id or "").strip() or None,
            "event_types": set(event_types or set()) or None,
        }

        matched = [
            event
            for event in list(self._event_buffer)
            if int(event.get("seq", 0)) > normalized_after and self._matches_filters(event, filters)
        ]
        if len(matched) > normalized_limit:
            return matched[-normalized_limit:]
        return matched

    def _normalize_payload(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        data = dict(payload or {})
        nested_payload = data.pop("payload", None)
        normalized_payload = dict(nested_payload) if isinstance(nested_payload, dict) else {}

        timestamp = data.pop("timestamp", time.time())
        session_id = data.pop("session_id", data.pop("ide_session_id", None))
        trace_id = data.pop("trace_id", None)
        task_id = data.pop("task_id", data.pop("turn_id", None))
        agent_id = data.pop("agent_id", None)
        status = data.pop("status", None)

        normalized_payload.update(data)
        normalized_payload["timestamp"] = timestamp
        normalized_payload["session_id"] = session_id
        normalized_payload["trace_id"] = trace_id
        normalized_payload["task_id"] = task_id
        normalized_payload["agent_id"] = agent_id
        normalized_payload["status"] = status
        return normalized_payload

    def _matches_filters(self, event: dict[str, Any], filters: dict[str, Any]) -> bool:
        session_filter = filters.get("session_id")
        if session_filter and str(event.get("session_id") or "") != session_filter:
            return False

        event_type_filter = filters.get("event_types")
        if event_type_filter and str(event.get("event_type") or "") not in event_type_filter:
            return False

        return True
