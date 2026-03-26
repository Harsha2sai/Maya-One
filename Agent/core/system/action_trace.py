from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from .system_models import SystemAction, SystemResult

logger = logging.getLogger(__name__)


@dataclass
class TraceEntry:
    timestamp: str
    trace_id: str
    action_type: str
    params: dict
    result_success: bool
    result_message: str
    screenshot_path: str = ""
    duration_ms: float = 0.0


class ActionTrace:
    _traces: list[TraceEntry] = []
    MAX_ENTRIES = 200

    @classmethod
    def record(
        cls,
        action: SystemAction,
        result: SystemResult,
        screenshot_path: str = "",
        duration_ms: float = 0.0,
    ) -> TraceEntry:
        entry = TraceEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            trace_id=str(action.trace_id or result.trace_id or ""),
            action_type=action.action_type.value,
            params=dict(action.params or {}),
            result_success=bool(result.success),
            result_message=str(result.message or ""),
            screenshot_path=str(screenshot_path or ""),
            duration_ms=float(duration_ms or 0.0),
        )
        cls._traces.append(entry)
        if len(cls._traces) > cls.MAX_ENTRIES:
            cls._traces.pop(0)
        logger.info(
            "action_trace_recorded trace_id=%s action=%s success=%s duration_ms=%.1f",
            entry.trace_id,
            entry.action_type,
            entry.result_success,
            entry.duration_ms,
        )
        return entry

    @classmethod
    def get_task_trace(cls, trace_id: str) -> list[TraceEntry]:
        target = str(trace_id or "").strip()
        return [entry for entry in cls._traces if entry.trace_id == target]
