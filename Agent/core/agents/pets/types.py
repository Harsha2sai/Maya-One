"""Agent Pets type definitions."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class PetType(str, Enum):
    """Types of specialist pets that can be spawned by subagents."""

    LINT = "lint"
    TEST = "test"
    SECURITY = "security"
    SUMMARIZE = "summarize"
    PATTERN = "pattern"
    FACT_CHECK = "fact_check"
    DESIGN = "design"
    SOURCE = "source"


@dataclass
class PetPersonality:
    """Personality traits that evolve based on task history."""

    thoroughness: float = 0.5
    speed: float = 0.5
    caution: float = 0.5
    creativity: float = 0.5


@dataclass
class PetInstance:
    """A pet instance with XP, level, and personality."""

    id: str
    pet_type: PetType
    parent_agent_type: str  # "coder", "reviewer", etc.
    xp: int = 0
    level: int = 1
    personality: PetPersonality = field(default_factory=PetPersonality)
    task_count: int = 0
    success_count: int = 0

    XP_PER_LEVEL = 50

    @property
    def success_rate(self) -> float:
        """Calculate success rate as a percentage."""
        if self.task_count == 0:
            return 1.0
        return self.success_count / self.task_count

    def gain_xp(self, amount: int) -> bool:
        """
        Add XP and check for level up.

        Returns:
            True if the pet leveled up.
        """
        self.xp += amount
        new_level = max(1, self.xp // self.XP_PER_LEVEL + 1)
        if new_level > self.level:
            self.level = new_level
            return True
        return False
