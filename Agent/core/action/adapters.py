"""Adapters between legacy route outputs and canonical action contracts."""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from core.action.models import ActionIntent, ToolReceipt, VerificationResult


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _requires_confirmation(operation: str, target: str) -> bool:
    op = _safe_str(operation).lower()
    tgt = _safe_str(target).lower()
    if op in {"delete_note", "delete_alarm", "delete_reminder", "delete_calendar_event"}:
        return True
    if op in {"close_app", "run_shell_command"} and tgt:
        return True
    return False


def _safe_confidence(raw_value: Any, default: float = 0.8) -> float:
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except Exception:
        return default


def from_direct_tool_intent(
    direct_tool_intent: Any,
    *,
    session_id: str,
    turn_id: str,
    trace_id: str,
    source_route: str = "fast_path",
) -> ActionIntent:
    tool_name = _safe_str(getattr(direct_tool_intent, "tool", ""))
    args = getattr(direct_tool_intent, "args", {}) or {}
    target = _safe_str(args.get("app_name") or args.get("folder_name") or args.get("command"))
    query = _safe_str(args.get("query"))
    entity = _safe_str(getattr(direct_tool_intent, "group", "")) or "tool"
    return ActionIntent(
        intent_id=_new_id("intent"),
        session_id=_safe_str(session_id) or "unknown_session",
        turn_id=_safe_str(turn_id) or "unknown_turn",
        trace_id=_safe_str(trace_id) or "unknown_trace",
        source_route=_safe_str(source_route) or "fast_path",
        target=target,
        operation=tool_name or "unknown_tool",
        entity=entity,
        query=query,
        confidence=1.0,
        requires_confirmation=_requires_confirmation(tool_name, target),
    )


def from_system_action(
    system_action: Any,
    *,
    session_id: str,
    turn_id: str,
    trace_id: str,
    source_route: str = "system",
) -> ActionIntent:
    if isinstance(system_action, dict):
        action_type = _safe_str(system_action.get("action_type") or system_action.get("tool_name"))
        target = _safe_str(system_action.get("target") or system_action.get("path") or system_action.get("app_name"))
        confidence = _safe_confidence(system_action.get("confidence"))
        entity = _safe_str(system_action.get("entity") or "system")
        query = _safe_str(system_action.get("query"))
    else:
        action_type = _safe_str(getattr(system_action, "action_type", None) or getattr(system_action, "tool_name", None))
        target = _safe_str(
            getattr(system_action, "target", None)
            or getattr(system_action, "path", None)
            or getattr(system_action, "app_name", None)
        )
        confidence = _safe_confidence(getattr(system_action, "confidence", None))
        entity = _safe_str(getattr(system_action, "entity", "system")) or "system"
        query = _safe_str(getattr(system_action, "query", ""))
    return ActionIntent(
        intent_id=_new_id("intent"),
        session_id=_safe_str(session_id) or "unknown_session",
        turn_id=_safe_str(turn_id) or "unknown_turn",
        trace_id=_safe_str(trace_id) or "unknown_trace",
        source_route=_safe_str(source_route) or "system",
        target=target,
        operation=action_type or "unknown_action",
        entity=entity,
        query=query,
        confidence=max(0.0, min(1.0, confidence)),
        requires_confirmation=_requires_confirmation(action_type, target),
    )


def to_tool_receipt(
    *,
    intent_id: str,
    tool_name: str,
    raw_result: Any,
    normalized_result: Optional[Dict[str, Any]],
    duration_ms: int,
    verification: Optional[VerificationResult] = None,
) -> ToolReceipt:
    normalized = dict(normalized_result or {})
    executed = raw_result is not None
    success = bool(normalized.get("success", executed))
    error_code = _safe_str(normalized.get("error_code"))
    message = _safe_str(normalized.get("message") or normalized.get("result"))
    if not executed:
        status = "not_executed"
    elif success:
        status = "succeeded"
    elif error_code:
        status = "failed"
    else:
        status = "inconclusive"
    return ToolReceipt(
        receipt_id=_new_id("receipt"),
        intent_id=_safe_str(intent_id) or _new_id("intent"),
        tool_name=_safe_str(tool_name) or "unknown_tool",
        success=success,
        status=status,
        executed=executed,
        error_code=error_code,
        message=message,
        raw_result=raw_result,
        normalized_result=normalized,
        duration_ms=max(0, int(duration_ms or 0)),
        verification=verification,
    )
