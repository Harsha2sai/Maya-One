"""Agent Pet implementation with XP and personality evolution."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from .types import PetInstance, PetPersonality, PetType

if TYPE_CHECKING:
    from core.agents.subagent import SubAgentManager


# Pet purpose prompts
PET_PROMPTS = {
    PetType.LINT: "You fix code style, imports, and formatting issues only. Be concise.",
    PetType.TEST: "You generate pytest unit tests for the given code. Happy path + edge cases.",
    PetType.SECURITY: "You scan for security vulnerabilities. Output: finding + severity + fix.",
    PetType.SUMMARIZE: "You produce a 3-sentence TL;DR of the given content.",
    PetType.PATTERN: "You identify anti-patterns and code smells. Output: pattern name + location.",
    PetType.FACT_CHECK: "You verify factual claims. Output: verified/unverified + source.",
    PetType.DESIGN: "You suggest design pattern improvements. Be specific and actionable.",
    PetType.SOURCE: "You verify citations and URLs. Output: valid/invalid/404 per source.",
}


class AgentPet:
    """
    Micro-specialist spawned by a SubAgent.

    Gains XP per task, evolves personality, upgrades prompt.
    """

    def __init__(self, pet_type: PetType, parent_agent_type: str):
        self.instance = PetInstance(
            id=f"pet-{uuid.uuid4().hex[:6]}",
            pet_type=pet_type,
            parent_agent_type=parent_agent_type,
        )

    async def execute(self, task: str, subagent_manager: SubAgentManager) -> str:
        """
        Run the pet's micro-task via a subagent spawn.

        Args:
            task: The task description.
            subagent_manager: The SubAgentManager to spawn with.

        Returns:
            The result of the task.
        """
        prompt = self._build_prompt()
        result = await subagent_manager.spawn(
            agent_type=self.instance.parent_agent_type,
            task=f"{prompt}\n\nTask: {task}",
            wait=True,
        )

        success = result.status.value == "completed"
        self.instance.task_count += 1
        if success:
            self.instance.success_count += 1

        leveled_up = self.instance.gain_xp(20 if success else 5)
        self._evolve_personality(success)

        return result.result or "(no output)"

    def _build_prompt(self) -> str:
        """Build the prompt for this pet based on level and history."""
        base = PET_PROMPTS.get(self.instance.pet_type, "You are a specialist assistant.")
        if self.instance.level >= 3:
            base += f" You have level {self.instance.level} expertise."
        if self.instance.success_rate > 0.9:
            base += " You are highly reliable."
        return base

    def _evolve_personality(self, success: bool):
        """Evolve personality traits based on task outcome."""
        p = self.instance.personality
        if self.instance.pet_type == PetType.SECURITY:
            p.caution = min(1.0, p.caution + 0.02)
        if success:
            p.thoroughness = min(1.0, p.thoroughness + 0.01)
        else:
            p.caution = min(1.0, p.caution + 0.05)

    @property
    def summary(self) -> str:
        """Get a formatted summary of this pet."""
        icon = ["🥚", "🐣", "🐦", "🦅", "🐉"][min(self.instance.level - 1, 4)]
        return (
            f"{icon} {self.instance.pet_type.value} pet "
            f"[Lvl {self.instance.level}] "
            f"XP:{self.instance.xp} "
            f"SR:{self.instance.success_rate:.0%}"
        )
