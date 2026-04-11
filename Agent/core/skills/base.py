"""Base skill contracts for reusable workflow execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class SkillPermissionLevel(str, Enum):
    SAFE = "safe"
    STORAGE = "storage"
    NETWORK = "network"
    SYSTEM = "system"
    ADMIN = "admin"


@dataclass
class SkillResult:
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": bool(self.success),
            "data": dict(self.data or {}),
            "error": self.error,
            "metadata": dict(self.metadata or {}),
        }


class BaseSkill(ABC):
    """Abstract base class for executable skills."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        permission_level: SkillPermissionLevel = SkillPermissionLevel.SAFE,
        permission_tool_name: Optional[str] = None,
    ) -> None:
        self.name = str(name or "").strip()
        self.description = str(description or "").strip()
        self.permission_level = SkillPermissionLevel(permission_level)
        self.permission_tool_name = str(permission_tool_name or self.name).strip().lower()

        if not self.name:
            raise ValueError("skill name is required")
        if not self.description:
            raise ValueError("skill description is required")

    def validate(self, params: Dict[str, Any]) -> bool:
        return isinstance(params, dict)

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> SkillResult:
        """Execute this skill and return a normalized result."""

    def metadata(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "permission_level": self.permission_level.value,
            "permission_tool_name": self.permission_tool_name,
        }
