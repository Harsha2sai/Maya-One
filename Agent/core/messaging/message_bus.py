"""In-process message bus with bounded queue and structured envelopes."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Set

from config.settings import settings

logger = logging.getLogger(__name__)

MessageHandler = Callable[["MessageEnvelope"], Awaitable[None] | None]


class MessageBusBackpressureError(RuntimeError):
    """Raised when publish is rejected due to queue depth limits."""


@dataclass
class MessageEnvelope:
    topic: str
    payload: Dict[str, Any]
    envelope_id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    ts: float = field(default_factory=lambda: float(time.time()))
    trace_id: str | None = None
    handoff_id: str | None = None
    task_id: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "ts": self.ts,
            "topic": self.topic,
            "payload": dict(self.payload or {}),
            "trace_id": self.trace_id,
            "handoff_id": self.handoff_id,
            "task_id": self.task_id,
            "metadata": dict(self.metadata or {}),
        }


class MessageBus:
    """Bounded in-process pub/sub transport for internal runtime events."""

    def __init__(self, max_queue_depth: int | None = None) -> None:
        resolved_depth = int(max_queue_depth or getattr(settings, "max_message_bus_queue_depth_global", 1000))
        self._queue: asyncio.Queue[MessageEnvelope] = asyncio.Queue(maxsize=max(1, resolved_depth))
        self._subscribers: Dict[str, Set[MessageHandler]] = {}
        self._drain_lock = asyncio.Lock()

    def subscribe(self, topic: str, handler: MessageHandler) -> None:
        normalized_topic = str(topic or "").strip()
        if not normalized_topic:
            raise ValueError("topic is required")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._subscribers.setdefault(normalized_topic, set()).add(handler)

    def unsubscribe(self, topic: str, handler: MessageHandler) -> None:
        normalized_topic = str(topic or "").strip()
        handlers = self._subscribers.get(normalized_topic)
        if not handlers:
            return
        handlers.discard(handler)
        if not handlers:
            self._subscribers.pop(normalized_topic, None)

    async def publish(
        self,
        topic: str,
        payload: Dict[str, Any] | None,
        *,
        trace_id: str | None = None,
        handoff_id: str | None = None,
        task_id: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        normalized_topic = str(topic or "").strip()
        if not normalized_topic:
            raise ValueError("topic is required")

        envelope = MessageEnvelope(
            topic=normalized_topic,
            payload=dict(payload or {}),
            trace_id=str(trace_id or "").strip() or None,
            handoff_id=str(handoff_id or "").strip() or None,
            task_id=str(task_id or "").strip() or None,
            metadata=dict(metadata or {}),
        )

        if self._queue.full():
            raise MessageBusBackpressureError(
                f"message_bus_queue_full topic={normalized_topic} depth={self._queue.maxsize}"
            )

        self._queue.put_nowait(envelope)
        await self._drain()
        return envelope.to_dict()

    async def _drain(self) -> None:
        if self._queue.empty():
            return
        async with self._drain_lock:
            while not self._queue.empty():
                envelope = self._queue.get_nowait()
                try:
                    await self._dispatch(envelope)
                finally:
                    self._queue.task_done()

    async def _dispatch(self, envelope: MessageEnvelope) -> None:
        handlers = list(self._subscribers.get(envelope.topic, set())) + list(self._subscribers.get("*", set()))
        if not handlers:
            return

        for handler in handlers:
            try:
                maybe = handler(envelope)
                if inspect.isawaitable(maybe):
                    await maybe
            except Exception as exc:
                logger.warning(
                    "message_bus_handler_failed topic=%s handler=%s error=%s",
                    envelope.topic,
                    getattr(handler, "__name__", repr(handler)),
                    exc,
                )
