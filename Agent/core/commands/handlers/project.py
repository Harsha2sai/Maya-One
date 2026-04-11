from __future__ import annotations


async def handle_project(args: str, context: dict) -> str:
    pm = context.get("project_mode")
    if not pm:
        return "Project mode not available."

    parts = str(args or "").strip().split(maxsplit=1)
    sub = parts[0].lower() if parts else "status"
    rest = parts[1] if len(parts) > 1 else ""

    if sub == "start":
        if not rest:
            return "Usage: /project start <name>"
        return await pm.start(rest)
    if sub == "status":
        return await pm.status()
    if sub == "cancel":
        return await pm.cancel()
    if sub == "next":
        return await pm.advance()
    if sub == "req":
        if not rest:
            return "Usage: /project req <requirement>"
        return await pm.add_requirement(rest)

    return (
        "Project mode commands:\n"
        "  /project start <name>\n"
        "  /project req <requirement>\n"
        "  /project next\n"
        "  /project status\n"
        "  /project cancel"
    )

