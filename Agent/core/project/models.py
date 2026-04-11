from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProjectPhase(str, Enum):
    REQUIREMENTS = "requirements"
    PRD_GENERATION = "prd_generation"
    PLANNING = "planning"
    EXECUTION = "execution"
    REVIEW = "review"
    COMPLETE = "complete"


@dataclass
class ProjectContext:
    name: str
    description: str = ""
    phase: ProjectPhase = ProjectPhase.REQUIREMENTS
    requirements: list[str] = field(default_factory=list)
    prd: Optional[str] = None
    plan_steps: list[str] = field(default_factory=list)
    agent_results: dict[str, str] = field(default_factory=dict)

