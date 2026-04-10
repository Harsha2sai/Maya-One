"""Hook action primitives and concrete side-effect actions."""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from core.governance.audit import audit_logger
from core.governance.types import UserRole
from core.skills import SkillExecutor, SkillResult


@dataclass
class ActionResult:
    success: bool
    action_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": bool(self.success),
            "action_type": self.action_type,
            "data": dict(self.data or {}),
            "error": self.error,
        }


class HookAction(ABC):
    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> ActionResult:
        """Execute a hook action against event context."""


class NotifyAction(HookAction):
    """Publish notification payloads to MessageBus."""

    def __init__(
        self,
        *,
        message_bus: Any = None,
        topic: str = "hook.events",
        payload_builder: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> None:
        self._message_bus = message_bus
        self.topic = str(topic or "hook.events")
        self._payload_builder = payload_builder

    async def execute(self, context: Dict[str, Any]) -> ActionResult:
        payload = self._build_payload(context)

        bus = self._message_bus
        if bus is None:
            return ActionResult(
                success=False,
                action_type="notify",
                error="message_bus_unavailable",
                data={"topic": self.topic, "payload": payload},
            )

        publish = getattr(bus, "publish", None)
        if not callable(publish):
            return ActionResult(
                success=False,
                action_type="notify",
                error="message_bus_publish_missing",
                data={"topic": self.topic, "payload": payload},
            )

        maybe = publish(self.topic, payload)
        result = await maybe if asyncio.iscoroutine(maybe) else maybe
        return ActionResult(
            success=True,
            action_type="notify",
            data={"topic": self.topic, "payload": payload, "publish_result": result},
        )

    def _build_payload(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if callable(self._payload_builder):
            try:
                built = self._payload_builder(dict(context or {}))
                if isinstance(built, dict):
                    return built
            except Exception:
                pass
        return {
            "event_type": context.get("event_type"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context": dict(context or {}),
        }


class SkillAction(HookAction):
    """Execute a skill through SkillExecutor when a hook fires."""

    def __init__(
        self,
        *,
        skill_name: str,
        skill_executor: Optional[SkillExecutor] = None,
        params_builder: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        user_role: Any = UserRole.USER,
    ) -> None:
        self.skill_name = str(skill_name or "").strip().lower()
        self._executor = skill_executor or SkillExecutor()
        self._params_builder = params_builder
        self._user_role = user_role

        if not self.skill_name:
            raise ValueError("skill_name is required")

    async def execute(self, context: Dict[str, Any]) -> ActionResult:
        params = self._build_params(context)
        result: SkillResult = await self._executor.execute(
            self.skill_name,
            params,
            user_role=self._user_role,
            context={"hook_action": True, "event_type": context.get("event_type")},
        )
        return ActionResult(
            success=bool(result.success),
            action_type="skill",
            data={
                "skill_name": self.skill_name,
                "skill_result": result.to_dict(),
                "params": params,
            },
            error=result.error,
        )

    def _build_params(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if callable(self._params_builder):
            built = self._params_builder(dict(context or {}))
            if isinstance(built, dict):
                return built
        return dict((context or {}).get("params") or {})


class LogAction(HookAction):
    """Write structured hook activity into audit log."""

    def __init__(self, *, event_name: str = "hook_action", logger: Any = None) -> None:
        self.event_name = str(event_name or "hook_action")
        self._logger = logger or audit_logger

    async def execute(self, context: Dict[str, Any]) -> ActionResult:
        entry = {
            "event": self.event_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": context.get("event_type"),
            "context": dict(context or {}),
        }

        self._logger.info(json.dumps(entry))
        return ActionResult(
            success=True,
            action_type="log",
            data={"entry": entry},
        )
