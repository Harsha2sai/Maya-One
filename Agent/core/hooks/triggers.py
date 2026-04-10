"""Hook trigger definitions for runtime event automation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

TASK_COMPLETE = "TASK_COMPLETE"
TASK_FAILED = "TASK_FAILED"
AGENT_HANDOFF = "AGENT_HANDOFF"
SKILL_EXECUTED = "SKILL_EXECUTED"
MESSAGE_RECEIVED = "MESSAGE_RECEIVED"

HookCondition = Callable[[Dict[str, Any]], bool]


@dataclass(frozen=True)
class HookTrigger:
    event_type: str
    condition: Optional[HookCondition] = None
    priority: int = 0

    def matches(self, event_type: str, context: Optional[Dict[str, Any]] = None) -> bool:
        if str(event_type or "").strip().upper() != str(self.event_type or "").strip().upper():
            return False

        if self.condition is None:
            return True

        try:
            return bool(self.condition(dict(context or {})))
        except Exception:
            return False
