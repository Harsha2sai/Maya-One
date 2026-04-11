from core.agents.subagent.manager import SubAgentManager
from core.buddy.evolution import BuddyEvolution
from core.buddy.memory import BuddyMemory
from core.buddy.task_router import BuddyTaskRouter
from core.buddy.terminal_ui import render_buddy, render_stage_up


class BuddyCompanion:
    def __init__(
        self,
        subagent_manager: SubAgentManager,
        db_path: str = "dev_maya_one.db",
    ):
        self._mem = BuddyMemory(db_path)
        self._evo = BuddyEvolution(self._mem)
        self._router = BuddyTaskRouter(subagent_manager)

    def status(self) -> str:
        return render_buddy(self._mem.load())

    async def on_task_complete(self, success: bool) -> str:
        event = "task_completed" if success else "task_failed"
        _xp, staged_up = self._evo.award_xp(event)
        state = self._mem.load()
        output = render_buddy(state)
        if staged_up:
            output += render_stage_up(state.stage, self._evo.get_stage_name(state.stage))
        return output

    async def on_team_coordinated(self) -> str:
        _xp, staged_up = self._evo.award_xp("team_coordinated")
        state = self._mem.load()
        output = render_buddy(state)
        if staged_up:
            output += render_stage_up(state.stage, self._evo.get_stage_name(state.stage))
        return output

    async def route_task(self, task: str, hint: str = "") -> str:
        result = await self._router.route(task, hint)
        await self.on_task_complete(success=bool(result))
        return result
