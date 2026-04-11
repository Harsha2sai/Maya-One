from __future__ import annotations

from core.buddy.terminal_ui import render_buddy


async def handle_buddy(args: str, context: dict) -> str:
    del args
    buddy = context.get("buddy")
    if not buddy:
        return "Buddy not available."
    return buddy.status()


async def handle_xp(args: str, context: dict) -> str:
    del args
    buddy = context.get("buddy")
    if not buddy:
        return "Buddy not available."

    state = buddy._mem.load()
    return f"XP: {state.xp}  Level: {state.level}  Stage: {state.stage}"


async def handle_evolve(args: str, context: dict) -> str:
    buddy = context.get("buddy")
    if not buddy:
        return "Buddy not available."

    event = str(args or "").strip() or "task_completed"
    _, staged = buddy._evo.award_xp(event)
    state = buddy._mem.load()
    if staged:
        return render_buddy(state)
    return f"No evolution yet. Current stage: {state.stage}"

