"""Internal supervisor signals used by Maya for specialist delegation."""

from __future__ import annotations

from typing import Any, Dict


async def transfer_to_research(
    reason: str,
    execution_mode: str,
    context_hint: str | None = None,
) -> Dict[str, Any]:
    return {
        "signal": "transfer_to_research",
        "reason": reason,
        "execution_mode": execution_mode,
        "context_hint": context_hint,
    }


async def transfer_to_system_operator(
    reason: str,
    execution_mode: str,
    context_hint: str | None = None,
) -> Dict[str, Any]:
    return {
        "signal": "transfer_to_system_operator",
        "reason": reason,
        "execution_mode": execution_mode,
        "context_hint": context_hint,
    }


async def transfer_to_planner(
    reason: str,
    execution_mode: str,
    context_hint: str | None = None,
) -> Dict[str, Any]:
    return {
        "signal": "transfer_to_planner",
        "reason": reason,
        "execution_mode": execution_mode,
        "context_hint": context_hint,
    }

