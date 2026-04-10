"""Hook registry and dispatcher for event-driven automation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional

from .actions import ActionResult, HookAction
from .triggers import HookTrigger


@dataclass
class HookBinding:
    trigger: HookTrigger
    action: HookAction


class HookRegistry:
    """Register hooks and fire matching actions in priority order."""

    def __init__(self) -> None:
        self._bindings: List[HookBinding] = []

    def register(self, trigger: HookTrigger, action: HookAction) -> None:
        self._bindings.append(HookBinding(trigger=trigger, action=action))

    def count(self) -> int:
        return len(self._bindings)

    def clear(self) -> None:
        self._bindings.clear()

    def list_bindings(self) -> List[HookBinding]:
        return list(self._bindings)

    async def fire(self, event_type: str, context: Optional[Dict] = None) -> Dict[str, object]:
        context_payload = dict(context or {})
        context_payload["event_type"] = str(event_type or "").strip().upper()

        matches = [
            binding
            for binding in self._bindings
            if binding.trigger.matches(context_payload["event_type"], context_payload)
        ]
        ordered = sorted(matches, key=lambda item: int(item.trigger.priority), reverse=True)

        results: List[ActionResult] = []
        for binding in ordered:
            try:
                maybe = binding.action.execute(dict(context_payload))
                action_result = await maybe if asyncio.iscoroutine(maybe) else maybe
            except Exception as exc:  # pragma: no cover - defensive
                action_result = ActionResult(
                    success=False,
                    action_type=binding.action.__class__.__name__.lower(),
                    error=f"action_execution_failed:{exc}",
                    data={"trigger_event": binding.trigger.event_type},
                )
            if not isinstance(action_result, ActionResult):
                action_result = ActionResult(
                    success=True,
                    action_type=binding.action.__class__.__name__.lower(),
                    data={"result": action_result},
                )
            results.append(action_result)

        return {
            "event_type": context_payload["event_type"],
            "matched": len(ordered),
            "executed": len(results),
            "results": [item.to_dict() for item in results],
            "success_count": sum(1 for item in results if item.success),
            "failure_count": sum(1 for item in results if not item.success),
        }
