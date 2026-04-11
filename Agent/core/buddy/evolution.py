from core.buddy.memory import BuddyMemory

STAGE_NAMES = {
    1: "Seedling",
    2: "Apprentice",
    3: "Companion",
    4: "Partner",
    5: "Sovereign",
}

XP_REWARDS = {
    "task_completed": 10,
    "task_failed": 2,
    "team_coordinated": 25,
    "ralph_recovery": 50,
    "mode_switched": 5,
}


class BuddyEvolution:
    def __init__(self, memory: BuddyMemory):
        self._mem = memory

    def award_xp(self, event: str) -> tuple[int, bool]:
        """Returns (new_xp_total, did_stage_up)."""
        state = self._mem.load()
        reward = XP_REWARDS.get(event, 0)
        state.xp += reward
        state.total_tasks += 1 if "task" in event else 0

        did_stage_up = False
        for stage, threshold in sorted(
            BuddyMemory.STAGE_THRESHOLDS.items(),
            reverse=True,
        ):
            if state.xp >= threshold and stage > state.stage:
                state.stage = stage
                did_stage_up = True
                break

        state.level = max(1, state.xp // BuddyMemory.XP_PER_LEVEL)
        self._mem.save(state)
        return state.xp, did_stage_up

    def get_stage_name(self, stage: int) -> str:
        return STAGE_NAMES.get(stage, "Unknown")
