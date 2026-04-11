from __future__ import annotations

from core.governance.gate import ExecutionGate
from core.permissions.contracts import PermissionMode


def _parse_mode(mode_raw: str) -> PermissionMode:
    normalized = str(mode_raw or "").strip()
    if not normalized:
        raise ValueError("mode is empty")

    aliases = {
        "acceptedits": PermissionMode.ACCEPT_EDITS,
        "accept_edits": PermissionMode.ACCEPT_EDITS,
        "dontask": PermissionMode.DONT_ASK,
        "dont_ask": PermissionMode.DONT_ASK,
        "bypass": PermissionMode.BYPASS,
        "bypasspermissions": PermissionMode.BYPASS,
    }

    mode = aliases.get(normalized.lower())
    if mode is not None:
        return mode

    try:
        return PermissionMode(normalized)
    except Exception:
        pass

    try:
        return PermissionMode[normalized.upper()]
    except Exception as exc:
        raise ValueError(f"unknown mode: {normalized}") from exc


async def handle_mode(args: str, context: dict) -> str:
    gate = context.get("execution_gate") or ExecutionGate

    normalized = str(args or "").strip()
    if not normalized:
        current = gate.get_mode() if gate else "unknown"
        return f"Current mode: {current}"

    if not gate:
        return "ExecutionGate not available."

    try:
        mode = _parse_mode(normalized)
        gate.set_mode(mode)
        return f"Mode set to: {mode.value}"
    except Exception as exc:
        return f"Failed to set mode: {exc}"


async def handle_lock(args: str, context: dict) -> str:
    del args
    gate = context.get("execution_gate") or ExecutionGate
    gate.set_mode(PermissionMode.LOCKED)
    return "Mode set to: locked"


async def handle_unlock(args: str, context: dict) -> str:
    del args
    gate = context.get("execution_gate") or ExecutionGate
    gate.set_mode(PermissionMode.DEFAULT)
    return "Mode set to: default"

