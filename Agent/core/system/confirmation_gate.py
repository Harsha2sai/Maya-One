from __future__ import annotations

import asyncio
import logging
from typing import Any

from .system_models import ConfirmationState, SystemAction

logger = logging.getLogger(__name__)


class ConfirmationGate:
    TIMEOUT_SECONDS = 30
    _pending: dict[str, dict[str, Any]] = {}
    _publisher: Any = None

    @classmethod
    def set_publisher(cls, publisher: Any) -> None:
        cls._publisher = publisher

    @classmethod
    async def request(cls, action: SystemAction, session: Any = None) -> ConfirmationState:
        if not action.requires_confirmation:
            return ConfirmationState.CONFIRMED

        task_id = str(action.trace_id or "")
        event = asyncio.Event()
        cls._pending[task_id] = {
            "event": event,
            "state": ConfirmationState.PENDING,
            "action": action,
        }

        if callable(cls._publisher):
            await cls._publisher(action, session)

        try:
            await asyncio.wait_for(event.wait(), timeout=cls.TIMEOUT_SECONDS)
            return cls._pending[task_id]["state"]
        except asyncio.TimeoutError:
            logger.warning("confirmation_timeout task_id=%s", task_id)
            return ConfirmationState.TIMEOUT
        finally:
            cls._pending.pop(task_id, None)

    @classmethod
    def respond(cls, task_id: str, confirmed: bool) -> None:
        pending = cls._pending.get(str(task_id or ""))
        if not pending:
            return
        pending["state"] = (
            ConfirmationState.CONFIRMED if confirmed else ConfirmationState.REJECTED
        )
        pending["event"].set()
