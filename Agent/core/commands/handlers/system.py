from __future__ import annotations

from core.governance.gate import ExecutionGate
from core.permissions.contracts import PermissionMode


async def handle_help(args: str, context: dict) -> str:
    del args
    registry = context.get("command_registry")
    if not registry:
        return "No commands registered."

    lines = ["Available commands:"]
    for name, cmd in sorted(registry.all().items()):
        lines.append(f"  /{name:<10} {cmd.description}")
    return "\n".join(lines)


async def handle_status(args: str, context: dict) -> str:
    del args
    parts = []
    buddy = context.get("buddy")
    if buddy:
        parts.append(buddy.status())

    gate = context.get("execution_gate") or ExecutionGate
    if gate:
        parts.append(f"Mode: {gate.get_mode()}")

    mgr = context.get("subagent_manager")
    if mgr:
        parts.append(f"Active agents: {len(getattr(mgr, 'active', {}))}")

    return "\n".join(parts) if parts else "Status unavailable."


async def handle_reset(args: str, context: dict) -> str:
    del args
    gate = context.get("execution_gate") or ExecutionGate
    gate.set_mode(PermissionMode.DEFAULT)
    return "System state reset to defaults."

