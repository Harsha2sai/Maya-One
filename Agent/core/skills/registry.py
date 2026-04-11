"""Skill registry for both legacy packaged skills and BaseSkill runtime skills."""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.governance.types import UserRole
from core.registry.tool_registry import ToolMetadata, get_registry
from core.utils.intent_utils import normalize_intent

from .base import BaseSkill, SkillPermissionLevel
from .schema import PermissionLevel, Skill as LegacySkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Unified registry for skills used by the runtime."""

    def __init__(self) -> None:
        self.tool_registry = get_registry()
        self.skills: Dict[str, LegacySkill] = {}
        self._base_skills: Dict[str, BaseSkill] = {}

    # BaseSkill API (Phase 7)
    def register(self, skill: BaseSkill, *, replace: bool = False) -> bool:
        if not isinstance(skill, BaseSkill):
            raise TypeError("skill must be BaseSkill")

        key = str(skill.name or "").strip().lower()
        if not key:
            raise ValueError("skill.name is required")

        if key in self._base_skills and not replace:
            return False

        self._base_skills[key] = skill
        return True

    def get(self, skill_name: str) -> Optional[BaseSkill]:
        key = str(skill_name or "").strip().lower()
        return self._base_skills.get(key)

    def unregister(self, skill_name: str) -> bool:
        key = str(skill_name or "").strip().lower()
        return self._base_skills.pop(key, None) is not None

    def list_skill_names(self) -> List[str]:
        return sorted(self._base_skills.keys())

    def list_by_permission(self, permission_level: SkillPermissionLevel | str) -> List[str]:
        if isinstance(permission_level, SkillPermissionLevel):
            level = permission_level
        else:
            level = SkillPermissionLevel(str(permission_level or "safe").strip().lower())
        return sorted(
            skill.name for skill in self._base_skills.values() if skill.permission_level == level
        )

    # Legacy packaged skill API (backward compatibility)
    def register_skill(self, skill: LegacySkill, user_role: UserRole = UserRole.GUEST) -> bool:
        try:
            if not skill.validate():
                logger.error("❌ Invalid skill structure: %s", skill.metadata.name)
                return False

            if not self._check_permissions(skill, user_role):
                logger.error("❌ Insufficient permissions to load skill: %s", skill.metadata.name)
                return False

            if skill.init_handler:
                skill.init_handler()

            for func in skill.functions:
                tool_meta = ToolMetadata(
                    name=f"{skill.metadata.name}.{func.name}",
                    description=func.description,
                    parameters=func.parameters,
                    required_params=func.required_params,
                    category="skill",
                )
                self.tool_registry.register_tool(tool_meta)

            self.skills[skill.metadata.name] = skill
            logger.info("✅ Registered legacy skill: %s (%s functions)", skill.metadata.name, len(skill.functions))
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("❌ Failed to register legacy skill %s: %s", getattr(skill.metadata, "name", "unknown"), exc)
            return False

    def _check_permissions(self, skill: LegacySkill, user_role: UserRole) -> bool:
        required_permissions = skill.metadata.permissions

        if PermissionLevel.ADMIN in required_permissions:
            return user_role == UserRole.ADMIN

        if PermissionLevel.SYSTEM in required_permissions:
            return user_role in [UserRole.USER, UserRole.TRUSTED, UserRole.ADMIN]

        return True

    def load_from_file(self, skill_path: Path, user_role: UserRole = UserRole.GUEST) -> bool:
        try:
            spec = importlib.util.spec_from_file_location("skill_module", skill_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules["skill_module"] = module
            assert spec and spec.loader
            spec.loader.exec_module(module)

            if not hasattr(module, "create_skill"):
                logger.error("❌ Skill file missing create_skill() function: %s", skill_path)
                return False

            skill = module.create_skill()
            return self.register_skill(skill, user_role)
        except Exception as exc:  # pragma: no cover - depends on user skill module
            logger.error("❌ Failed to load skill from %s: %s", skill_path, exc)
            return False

    def unload_skill(self, skill_name: str) -> bool:
        if skill_name not in self.skills:
            return False

        skill = self.skills[skill_name]
        if skill.cleanup_handler:
            try:
                skill.cleanup_handler()
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("⚠️ Skill cleanup failed: %s", exc)

        del self.skills[skill_name]
        logger.info("🗑️ Unloaded legacy skill: %s", skill_name)
        return True

    def list_skills(self) -> List[Dict]:
        legacy_rows = [
            {
                "name": skill.metadata.name,
                "version": skill.metadata.version,
                "description": skill.metadata.description,
                "functions": len(skill.functions),
                "permissions": [normalize_intent(p) for p in skill.metadata.permissions],
                "source": "legacy",
            }
            for skill in self.skills.values()
        ]
        base_rows = [
            {
                "name": skill.name,
                "version": "phase7",
                "description": skill.description,
                "functions": 1,
                "permissions": [skill.permission_level.value],
                "source": "base",
            }
            for skill in self._base_skills.values()
        ]
        return sorted(legacy_rows + base_rows, key=lambda row: row["name"])

    def get_skill_function(self, tool_name: str) -> Optional[Callable]:
        if "." not in tool_name:
            return None

        skill_name, func_name = tool_name.split(".", 1)
        if skill_name in self.skills:
            for func in self.skills[skill_name].functions:
                if func.name == func_name:
                    return func.handler
        return None


_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry
