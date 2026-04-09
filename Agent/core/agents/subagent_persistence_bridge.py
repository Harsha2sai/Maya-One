"""Persistence bridge for subagent checkpoint, recovery, and $ralph mode."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from core.agents.subagent_manager import SubAgentManager


class RecoveryPolicy(str, Enum):
    NEVER = "never"
    ON_FAILURE = "on_failure"
    ALWAYS = "always"


@dataclass
class RecoverySnapshot:
    agent_id: str
    state: Dict[str, Any]
    recovery_policy: RecoveryPolicy = RecoveryPolicy.NEVER
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "state": dict(self.state or {}),
            "recovery_policy": self.recovery_policy.value,
            "updated_at": float(self.updated_at),
        }


class SubagentPersistenceBridge:
    """Connect subagent lifecycle to TaskPersistence."""

    def __init__(
        self,
        *,
        persistence: Any = None,
        subagent_manager: Optional["SubAgentManager"] = None,
    ) -> None:
        self._persistence = persistence
        self._subagent_manager = subagent_manager
        self._snapshots: Dict[str, RecoverySnapshot] = {}

    async def save_checkpoint(
        self,
        agent_id: str,
        state: Dict[str, Any],
    ) -> None:
        """Save subagent state for recovery."""
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            raise ValueError("agent_id is required")

        snapshot = RecoverySnapshot(
            agent_id=normalized_agent_id,
            state=self._to_jsonable(state),
            recovery_policy=self._get_recovery_policy(normalized_agent_id),
            updated_at=float(time.time()),
        )
        self._snapshots[normalized_agent_id] = snapshot

        if self._persistence is None:
            return

        save_checkpoint = getattr(self._persistence, "save_checkpoint", None)
        if callable(save_checkpoint):
            task_id = str((snapshot.state or {}).get("task_id") or normalized_agent_id)
            maybe = save_checkpoint(
                task_id=task_id,
                step_id=normalized_agent_id,
                payload={
                    "event": "subagent_recovery_checkpoint",
                    "agent_id": normalized_agent_id,
                    "recovery_policy": snapshot.recovery_policy.value,
                    "state": snapshot.state,
                    "updated_at": snapshot.updated_at,
                },
            )
            if asyncio.iscoroutine(maybe):
                await maybe

    async def resume_from_checkpoint(
        self,
        agent_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Recover subagent after restart ($ralph mode)."""
        snapshot = await self._load_snapshot(agent_id)
        if snapshot is None:
            return None
        if snapshot.recovery_policy == RecoveryPolicy.NEVER:
            return None

        state = dict(snapshot.state or {})
        if str(state.get("status") or "").strip().lower() in {"completed", "failed", "terminated"}:
            return None

        if self._subagent_manager is None:
            return {
                "agent_id": snapshot.agent_id,
                "recovered": True,
                "state": state,
                "recovery_policy": snapshot.recovery_policy.value,
            }

        task_context = dict(state.get("task_context") or {})
        if not task_context:
            task_context = {
                "agent_id": snapshot.agent_id,
                "parent_handoff_id": state.get("parent_handoff_id"),
                "delegation_chain_id": state.get("delegation_chain_id"),
                "task_id": state.get("task_id"),
                "trace_id": state.get("trace_id"),
                "conversation_id": state.get("conversation_id"),
            }
        else:
            task_context["agent_id"] = snapshot.agent_id

        resumed = await self._subagent_manager.spawn(
            str(state.get("agent_type") or "").strip(),
            task_context,
            worktree_path=state.get("worktree_path"),
            recoverable=snapshot.recovery_policy != RecoveryPolicy.NEVER,
        )
        resumed.setdefault("metadata", {})
        resumed["metadata"]["recovered_from_agent_id"] = snapshot.agent_id
        resumed["metadata"]["recovery_policy"] = snapshot.recovery_policy.value
        return resumed

    async def mark_recoverable(
        self,
        agent_id: str,
        recovery_policy: RecoveryPolicy,
    ) -> None:
        """Enable $ralph mode for this subagent."""
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            raise ValueError("agent_id is required")

        snapshot = self._snapshots.get(normalized_agent_id)
        if snapshot is None:
            snapshot = RecoverySnapshot(
                agent_id=normalized_agent_id,
                state={"agent_id": normalized_agent_id},
                recovery_policy=RecoveryPolicy(recovery_policy),
                updated_at=float(time.time()),
            )
            self._snapshots[normalized_agent_id] = snapshot
        else:
            snapshot.recovery_policy = RecoveryPolicy(recovery_policy)
            snapshot.updated_at = float(time.time())

        if self._persistence is None:
            return

        save_checkpoint = getattr(self._persistence, "save_checkpoint", None)
        if callable(save_checkpoint):
            task_id = str((snapshot.state or {}).get("task_id") or normalized_agent_id)
            maybe = save_checkpoint(
                task_id=task_id,
                step_id=normalized_agent_id,
                payload={
                    "event": "subagent_marked_recoverable",
                    "agent_id": normalized_agent_id,
                    "recovery_policy": snapshot.recovery_policy.value,
                    "updated_at": snapshot.updated_at,
                },
            )
            if asyncio.iscoroutine(maybe):
                await maybe

    async def _load_snapshot(self, agent_id: str) -> Optional[RecoverySnapshot]:
        normalized_agent_id = str(agent_id or "").strip()
        if not normalized_agent_id:
            return None

        snapshot = self._snapshots.get(normalized_agent_id)
        if snapshot is not None:
            return snapshot

        if self._persistence is None:
            return None

        for method_name in ("load_checkpoint", "get_checkpoint", "read_checkpoint"):
            method = getattr(self._persistence, method_name, None)
            if not callable(method):
                continue
            maybe = method(normalized_agent_id)
            payload = await maybe if asyncio.iscoroutine(maybe) else maybe
            snapshot = self._snapshot_from_payload(normalized_agent_id, payload)
            if snapshot is not None:
                self._snapshots[normalized_agent_id] = snapshot
                return snapshot

        return None

    async def get_snapshot(self, agent_id: str) -> Optional[Dict[str, Any]]:
        snapshot = await self._load_snapshot(agent_id)
        if snapshot is None:
            return None
        return snapshot.to_dict()

    def _get_recovery_policy(self, agent_id: str) -> RecoveryPolicy:
        snapshot = self._snapshots.get(agent_id)
        if snapshot is None:
            return RecoveryPolicy.NEVER
        return snapshot.recovery_policy

    @staticmethod
    def _snapshot_from_payload(agent_id: str, payload: Any) -> Optional[RecoverySnapshot]:
        if not isinstance(payload, dict):
            return None
        if "state" in payload:
            state = payload.get("state")
            policy = payload.get("recovery_policy") or RecoveryPolicy.NEVER.value
            updated_at = float(payload.get("updated_at") or time.time())
            return RecoverySnapshot(
                agent_id=agent_id,
                state=SubagentPersistenceBridge._to_jsonable(state),
                recovery_policy=RecoveryPolicy(str(policy)),
                updated_at=updated_at,
            )
        return None

    @staticmethod
    def _to_jsonable(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): SubagentPersistenceBridge._to_jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [SubagentPersistenceBridge._to_jsonable(v) for v in value]
        if hasattr(value, "to_dict") and callable(value.to_dict):
            try:
                return SubagentPersistenceBridge._to_jsonable(value.to_dict())
            except Exception:
                return str(value)
        if hasattr(value, "__dict__"):
            try:
                return SubagentPersistenceBridge._to_jsonable(dict(value.__dict__))
            except Exception:
                return str(value)
        return str(value)
