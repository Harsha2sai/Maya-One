from __future__ import annotations

from typing import Optional

from core.project.models import ProjectContext, ProjectPhase


class ProjectModeOrchestrator:
    """
    Orchestrates a full project lifecycle:
    Requirements -> PRD -> Plan -> Execute -> Review.
    """

    def __init__(self, subagent_manager, buddy, command_registry):
        self._agents = subagent_manager
        self._buddy = buddy
        self._cmds = command_registry
        self._active: Optional[ProjectContext] = None

    def is_active(self) -> bool:
        return self._active is not None

    def current_phase(self) -> Optional[ProjectPhase]:
        return self._active.phase if self._active else None

    async def start(self, project_name: str, description: str = "") -> str:
        if self._active:
            return f"Project '{self._active.name}' already in progress. Use /project status."
        self._active = ProjectContext(name=project_name, description=description)
        return (
            f"Project '{project_name}' started.\n"
            f"Phase: {ProjectPhase.REQUIREMENTS.value}\n"
            "Tell me the requirements one at a time. Say 'done' when finished."
        )

    async def add_requirement(self, requirement: str) -> str:
        if not self._active:
            return "No active project. Use /project start <name>."
        self._active.requirements.append(requirement)
        count = len(self._active.requirements)
        return f"Requirement {count} recorded. Add more or say 'done'."

    async def advance(self) -> str:
        if not self._active:
            return "No active project."

        phase = self._active.phase

        if phase == ProjectPhase.REQUIREMENTS:
            if not self._active.requirements:
                return "No requirements recorded yet."
            self._active.phase = ProjectPhase.PRD_GENERATION
            return await self._generate_prd()

        if phase == ProjectPhase.PRD_GENERATION:
            self._active.phase = ProjectPhase.PLANNING
            return await self._generate_plan()

        if phase == ProjectPhase.PLANNING:
            self._active.phase = ProjectPhase.EXECUTION
            return await self._execute_plan()

        if phase == ProjectPhase.EXECUTION:
            self._active.phase = ProjectPhase.REVIEW
            return await self._review()

        if phase == ProjectPhase.REVIEW:
            self._active.phase = ProjectPhase.COMPLETE
            name = self._active.name
            self._active = None
            return f"Project '{name}' complete."

        return "Project already complete."

    async def _generate_prd(self) -> str:
        reqs = "\n".join(f"- {r}" for r in self._active.requirements)
        task = (
            f"Generate a concise PRD for project '{self._active.name}'.\n"
            f"Requirements:\n{reqs}\n"
            "Include: overview, goals, scope, success criteria."
        )
        instance = await self._agents.spawn(
            agent_type="architect",
            task=task,
            wait=True,
        )
        self._active.prd = instance.result or ""
        await self._buddy.on_task_complete(success=bool(self._active.prd))
        return f"PRD generated.\n\n{self._active.prd[:500]}...\n\nSay 'next' to proceed to planning."

    async def _generate_plan(self) -> str:
        task = (
            "Break down this PRD into an ordered execution plan "
            f"with concrete steps:\n{self._active.prd}"
        )
        instance = await self._agents.spawn(
            agent_type="architect",
            task=task,
            wait=True,
        )
        raw = instance.result or ""
        self._active.plan_steps = [
            line.strip()
            for line in raw.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        return (
            f"Plan generated: {len(self._active.plan_steps)} steps.\n"
            "Say 'next' to begin execution."
        )

    async def _execute_plan(self) -> str:
        results = []
        for i, step in enumerate(self._active.plan_steps[:3], 1):
            instance = await self._agents.spawn(
                agent_type="coder",
                task=step,
                wait=True,
            )
            self._active.agent_results[f"step_{i}"] = instance.result or ""
            results.append(f"Step {i}: {'OK' if instance.result else 'empty'}")
            await self._buddy.on_task_complete(success=bool(instance.result))
        return "Execution complete:\n" + "\n".join(results) + "\n\nSay 'next' to review."

    async def _review(self) -> str:
        summary = "\n".join(
            f"{k}: {v[:100]}" for k, v in self._active.agent_results.items()
        )
        task = f"Review these execution results and summarize quality:\n{summary}"
        instance = await self._agents.spawn(
            agent_type="reviewer",
            task=task,
            wait=True,
        )
        await self._buddy.on_team_coordinated()
        return (
            f"Review complete:\n{instance.result or 'No review generated'}\n\n"
            "Say 'next' to close the project."
        )

    async def status(self) -> str:
        if not self._active:
            return "No active project."
        p = self._active
        return (
            f"Project: {p.name}\n"
            f"Phase: {p.phase.value}\n"
            f"Requirements: {len(p.requirements)}\n"
            f"Plan steps: {len(p.plan_steps)}\n"
            f"PRD: {'yes' if p.prd else 'no'}"
        )

    async def cancel(self) -> str:
        if not self._active:
            return "No active project to cancel."
        name = self._active.name
        self._active = None
        return f"Project '{name}' cancelled."

