"""In-process message bus with bounded queues and correlation envelopes."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from config.settings import settings
from core.observability.trace_context import current_trace_id
from core.telemetry.runtime_metrics import RuntimeMetrics

logger = logging.getLogger(__name__)

DEFAULT_CHANNELS = {
    "agent.command",
    "agent.progress",
    "agent.result",
    "agent.error",
}

MessageHandler = Callable[["MessageEnvelope"], Awaitable[None] | None]


class MessageBusBackpressureError(RuntimeError):
    """Raised when global queue depth exceeds configured limits."""

    code = "message_bus_queue_limit_exceeded"


@dataclass
class MessageEnvelope:
    channel: str
    payload: Dict[str, Any]
    trace_id: str
    handoff_id: str
    task_id: str
    message_id: str
    timestamp: float
    checkpoint_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "payload": dict(self.payload or {}),
            "trace_id": self.trace_id,
            "handoff_id": self.handoff_id,
            "task_id": self.task_id,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "checkpoint_id": self.checkpoint_id,
            "metadata": dict(self.metadata or {}),
        }


class MessageBus:
    """Simple in-process pub/sub with bounded queue depth."""

    def __init__(self, *, max_queue_depth: Optional[int] = None) -> None:
        self._subscribers: Dict[str, List[MessageHandler]] = {}
        self._lock = asyncio.Lock()
        self._inflight = 0
        self._max_queue_depth = int(
            max_queue_depth
            if max_queue_depth is not None
            else getattr(settings, "max_message_bus_queue_depth_global", 1000)
        )
        for channel in DEFAULT_CHANNELS:
            self._subscribers[channel] = []

    @property
    def max_queue_depth(self) -> int:
        return self._max_queue_depth

    @property
    def inflight(self) -> int:
        return self._inflight

    async def subscribe(self, channel: str, handler: MessageHandler) -> None:
        normalized = str(channel or "").strip()
        if not normalized:
            raise ValueError("channel is required")
        async with self._lock:
            handlers = self._subscribers.setdefault(normalized, [])
            if handler not in handlers:
                handlers.append(handler)
                logger.info("message_bus_subscribed channel=%s handlers=%s", normalized, len(handlers))

    async def unsubscribe(self, channel: str, handler: MessageHandler) -> None:
        normalized = str(channel or "").strip()
        if not normalized:
            return
        async with self._lock:
            handlers = self._subscribers.get(normalized) or []
            if handler in handlers:
                handlers.remove(handler)
                logger.info("message_bus_unsubscribed channel=%s handlers=%s", normalized, len(handlers))

    async def publish(
        self,
        channel: str,
        payload: Dict[str, Any],
        *,
        trace_id: str = "",
        handoff_id: str = "",
        task_id: str = "",
        message_id: str = "",
        checkpoint_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MessageEnvelope:
        normalized_channel = str(channel or "").strip()
        if not normalized_channel:
            raise ValueError("channel is required")
        if self._inflight >= self._max_queue_depth:
            logger.warning(
                "message_bus_backpressure_rejected channel=%s inflight=%s max=%s",
                normalized_channel,
                self._inflight,
                self._max_queue_depth,
            )
            raise MessageBusBackpressureError(MessageBusBackpressureError.code)

        envelope = MessageEnvelope(
            channel=normalized_channel,
            payload=dict(payload or {}),
            trace_id=str(trace_id or "").strip() or current_trace_id(),
            handoff_id=str(handoff_id or "").strip(),
            task_id=str(task_id or "").strip(),
            message_id=str(message_id or "").strip() or f"msg_{uuid.uuid4().hex[:12]}",
            timestamp=float(time.time()),
            checkpoint_id=str(checkpoint_id or "").strip(),
            metadata=dict(metadata or {}),
        )

        async with self._lock:
            handlers = list(self._subscribers.get(normalized_channel) or [])
            self._inflight += 1
            RuntimeMetrics.increment("message_bus_queue_depth", 1)

        try:
            if not handlers:
                logger.debug("message_bus_no_subscribers channel=%s", normalized_channel)
                return envelope

            for handler in handlers:
                try:
                    maybe = handler(envelope)
                    if asyncio.iscoroutine(maybe):
                        await maybe
                except Exception as err:
                    logger.error(
                        "message_bus_handler_failed channel=%s message_id=%s error=%s",
                        normalized_channel,
                        envelope.message_id,
                        err,
                    )
            return envelope
        finally:
            async with self._lock:
                self._inflight = max(0, self._inflight - 1)
                RuntimeMetrics.increment("message_bus_queue_depth", -1)
