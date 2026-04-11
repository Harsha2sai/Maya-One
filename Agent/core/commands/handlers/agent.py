from __future__ import annotations


async def handle_spawn(args: str, context: dict) -> str:
    """Usage: /spawn <type> <task>"""
    parts = str(args or "").split(maxsplit=1)
    if len(parts) < 2:
        return "Usage: /spawn <type> <task>\nTypes: coder, reviewer, researcher, architect, tester"

    agent_type, task = parts[0], parts[1]
    mgr = context.get("subagent_manager")
    if not mgr:
        return "SubAgentManager not available"

    instance = await mgr.spawn(agent_type=agent_type, task=task, wait=False)
    return f"Spawned {agent_type} agent [{instance.id}] in background. Use /agents to check status."


async def handle_agents(args: str, context: dict) -> str:
    del args
    mgr = context.get("subagent_manager")
    if not mgr or not getattr(mgr, "active", None):
        return "No active agents."

    lines = []
    for aid, inst in mgr.active.items():
        status_value = getattr(getattr(inst, "status", None), "value", str(getattr(inst, "status", "unknown")))
        lines.append(f"  [{aid}] {inst.agent_type} - {status_value}")
    return "Active agents:\n" + "\n".join(lines)


async def handle_kill(args: str, context: dict) -> str:
    agent_id = str(args or "").strip()
    if not agent_id:
        return "Usage: /kill <agent_id>"

    mgr = context.get("subagent_manager")
    if not mgr:
        return "SubAgentManager not available"

    inst = getattr(mgr, "active", {}).pop(agent_id, None)
    if not inst:
        return f"Agent {agent_id} not found."

    await mgr._cleanup(inst)
    return f"Agent {agent_id} terminated."

