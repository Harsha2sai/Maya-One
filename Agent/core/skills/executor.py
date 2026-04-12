"""Skill execution runtime with permission-gated dispatch."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from core.governance.types import UserRole
from core.permissions.contracts import PermissionChecker, PermissionMode

from .base import BaseSkill, SkillPermissionLevel, SkillResult
from .registry import SkillRegistry, get_skill_registry


class SkillExecutor:
    """Execute skills from registry after permission checks."""

    _MIN_ROLE_BY_LEVEL = {
        SkillPermissionLevel.SAFE: UserRole.GUEST,
        SkillPermissionLevel.NETWORK: UserRole.USER,
        SkillPermissionLevel.STORAGE: UserRole.USER,
        SkillPermissionLevel.SYSTEM: UserRole.TRUSTED,
        SkillPermissionLevel.ADMIN: UserRole.ADMIN,
    }

    def __init__(
        self,
        *,
        registry: Optional[SkillRegistry] = None,
        permission_checker: Optional[PermissionChecker] = None,
    ) -> None:
        self.registry = registry or get_skill_registry()
        self.permission_checker = permission_checker or PermissionChecker()

    async def execute(
        self,
        skill_name: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        user_role: Any = UserRole.USER,
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        normalized_name = str(skill_name or "").strip().lower()
        payload = dict(params or {})

        skill = self.registry.get(normalized_name)
        if skill is None:
            return SkillResult(success=False, error=f"skill_not_found:{normalized_name}")

        if not skill.validate(payload):
            return SkillResult(success=False, error=f"invalid_skill_params:{normalized_name}")

        role = self._coerce_role(user_role)
        if not self._role_allows(skill.permission_level, role):
            return SkillResult(
                success=False,
                error=(
                    f"permission_denied:role_tier_required:{skill.permission_level.value}"
                ),
            )

        permission_result = self.permission_checker.check(
            skill.permission_tool_name,
            role,
            {
                "mode": PermissionMode.DEFAULT,
                "respect_mode_policy": False,
                **dict(context or {}),
            },
        )
        if not permission_result.allowed:
            return SkillResult(
                success=False,
                error=f"permission_denied:{permission_result.reason or 'blocked'}",
                metadata={"mode": permission_result.mode.value},
            )

        try:
            maybe = skill.execute(payload)
            result = await maybe if asyncio.iscoroutine(maybe) else maybe
        except Exception as exc:  # pragma: no cover - defensive
            return SkillResult(success=False, error=f"skill_execution_failed:{exc}")

        if isinstance(result, SkillResult):
            return result

        if isinstance(result, dict):
            return SkillResult(success=True, data=result)

        return SkillResult(success=True, data={"result": result})

    @classmethod
    def _role_allows(cls, level: SkillPermissionLevel, role: UserRole) -> bool:
        min_role = cls._MIN_ROLE_BY_LEVEL[SkillPermissionLevel(level)]
        return int(role) >= int(min_role)

    @staticmethod
    def _coerce_role(value: Any) -> UserRole:
        if isinstance(value, UserRole):
            return value
        if isinstance(value, int):
            try:
                return UserRole(value)
            except Exception:
                return UserRole.GUEST

        normalized = str(value or "").strip().upper()
        aliases = {
            "MEMBER": UserRole.USER,
            "TRUSTED": UserRole.TRUSTED,
            "USER": UserRole.USER,
            "GUEST": UserRole.GUEST,
            "ADMIN": UserRole.ADMIN,
        }
        return aliases.get(normalized, UserRole.GUEST)
