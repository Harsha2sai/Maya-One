from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any


IDEEventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class IDEStateBus:
    def __init__(self, queue_size: int = 200) -> None:
        self._queue_size = max(1, int(queue_size))
        self._queues: list[asyncio.Queue[dict[str, Any]]] = []
        self._handlers: list[IDEEventHandler] = []

    async def emit(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "event_type": str(event_type),
            "payload": dict(payload or {}),
            "timestamp": time.time(),
        }
        for queue in list(self._queues):
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

    def subscribe(self, handler: IDEEventHandler | None = None) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        self._queues.append(queue)
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
        if handler is not None and handler in self._handlers:
            self._handlers.remove(handler)

