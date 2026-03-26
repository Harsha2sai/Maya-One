"""
Lightweight per-request trace context propagation.
"""

from __future__ import annotations

import contextvars
import logging
import uuid
from typing import Any, Dict, Optional

_TRACE_CONTEXT: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "trace_context",
    default={},
)


REQUIRED_FIELDS = ("trace_id", "session_id", "user_id", "task_id")
_TRACE_LOGGING_ENABLED = False


class _TraceContextLogFilter(logging.Filter):
    """Inject trace context on every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = get_trace_context()
        trace_id = str(ctx.get("trace_id") or "").strip() or current_trace_id()
        record.trace_id = trace_id
        record.session_id = str(ctx.get("session_id") or "")
        record.user_id = str(ctx.get("user_id") or "")
        record.task_id = str(ctx.get("task_id") or "")
        return True


def _normalize(ctx: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for k, v in (ctx or {}).items():
        if v is None:
            continue
        normalized[str(k)] = v
    return normalized


def get_trace_context() -> Dict[str, Any]:
    return dict(_TRACE_CONTEXT.get() or {})


def current_trace_id() -> str:
    ctx = get_trace_context()
    trace_id = str(ctx.get("trace_id") or "").strip()
    if not trace_id:
        trace_id = str(uuid.uuid4())
        set_trace_context(trace_id=trace_id)
    return trace_id


def set_trace_context(**kwargs: Any) -> Dict[str, Any]:
    current = get_trace_context()
    current.update(_normalize(kwargs))
    if not str(current.get("trace_id") or "").strip():
        current["trace_id"] = str(uuid.uuid4())
    _TRACE_CONTEXT.set(current)
    return current


def start_trace(
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    task_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    return set_trace_context(
        trace_id=trace_id or str(uuid.uuid4()),
        session_id=session_id,
        user_id=user_id,
        task_id=task_id,
    )


def clear_trace_context() -> None:
    _TRACE_CONTEXT.set({})


def enable_trace_logging() -> None:
    """
    Ensure all logs include structured trace context fields.
    Safe to call multiple times.
    """
    global _TRACE_LOGGING_ENABLED
    if _TRACE_LOGGING_ENABLED:
        return

    root_logger = logging.getLogger()
    trace_filter = _TraceContextLogFilter()
    root_logger.addFilter(trace_filter)

    for handler in root_logger.handlers:
        handler.addFilter(trace_filter)
        fmt = getattr(getattr(handler, "formatter", None), "_fmt", "") or ""
        if "%(trace_id)" in fmt:
            continue
        if fmt:
            new_fmt = f"{fmt} trace_id=%(trace_id)s"
        else:
            new_fmt = "%(levelname)s:%(name)s:%(message)s trace_id=%(trace_id)s"
        handler.setFormatter(logging.Formatter(new_fmt))

    _TRACE_LOGGING_ENABLED = True
