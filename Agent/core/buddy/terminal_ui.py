from core.buddy.memory import BuddyState

STAGE_AVATARS = {
    1: "*",
    2: "o",
    3: "O",
    4: "@",
    5: "#",
}


def render_buddy(state: BuddyState) -> str:
    avatar = STAGE_AVATARS.get(state.stage, "?")
    bar_filled = min(10, state.xp % 100 // 10)
    bar = "#" * bar_filled + "." * (10 - bar_filled)
    return (
        f"{avatar} Buddy  Stage {state.stage}  "
        f"Lvl {state.level}  [{bar}]  {state.xp} XP"
    )


def render_stage_up(stage: int, name: str) -> str:
    avatar = STAGE_AVATARS.get(stage, "#")
    return f"\n{'=' * 40}\n{avatar}  BUDDY EVOLVED -> {name}!\n{'=' * 40}\n"
