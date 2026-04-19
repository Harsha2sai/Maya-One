from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ActionEnvelope:
    type: str
    target: str
    operation: str
    arguments: dict[str, Any]
    confidence: float
    reason: str


@dataclass(slots=True)
class GuardDecision:
    risk: str
    allowed: bool
    requires_approval: bool
    policy_reason: str


class ActionGuard:
    def check(self, action_envelope: ActionEnvelope | dict[str, Any]) -> GuardDecision:
        envelope = (
            action_envelope
            if isinstance(action_envelope, ActionEnvelope)
            else ActionEnvelope(
                type=str(action_envelope.get("type", "")),
                target=str(action_envelope.get("target", "")),
                operation=str(action_envelope.get("operation", "")),
                arguments=dict(action_envelope.get("arguments") or {}),
                confidence=float(action_envelope.get("confidence") or 0.0),
                reason=str(action_envelope.get("reason", "")),
            )
        )

        if self._contains_traversal(envelope.arguments):
            return GuardDecision(
                risk="high",
                allowed=False,
                requires_approval=False,
                policy_reason="path traversal detected in arguments",
            )

        target = envelope.target.lower().strip()
        operation = envelope.operation.lower().strip()

        if target == "file" and operation == "read":
            return GuardDecision(
                risk="low",
                allowed=True,
                requires_approval=False,
                policy_reason="file read operation allowed",
            )
        if target == "file" and operation == "write":
            return GuardDecision(
                risk="medium",
                allowed=True,
                requires_approval=False,
                policy_reason="file write allowed in workspace scope",
            )
        if target == "terminal" and operation == "exec":
            return GuardDecision(
                risk="high",
                allowed=True,
                requires_approval=True,
                policy_reason="terminal execution requires explicit approval",
            )

        return GuardDecision(
            risk="high",
            allowed=False,
            requires_approval=False,
            policy_reason=f"unsupported operation: target={target} operation={operation}",
        )

    def _contains_traversal(self, value: Any) -> bool:
        if isinstance(value, dict):
            return any(self._contains_traversal(v) for v in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(self._contains_traversal(v) for v in value)
        if isinstance(value, str):
            return ".." in value
        return False

