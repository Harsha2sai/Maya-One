from core.agents.subagent.manager import SubAgentManager

TASK_ROUTING = {
    "code": "coder",
    "review": "reviewer",
    "research": "researcher",
    "plan": "architect",
    "test": "tester",
    "security": "security",
    "docs": "documentation",
}


class BuddyTaskRouter:
    def __init__(self, subagent_manager: SubAgentManager):
        self._mgr = subagent_manager

    async def route(self, task: str, hint: str = "") -> str:
        agent_type = TASK_ROUTING.get(hint, "researcher")
        instance = await self._mgr.spawn(
            agent_type=agent_type,
            task=task,
            wait=True,
        )
        return instance.result or instance.error or "No result"
