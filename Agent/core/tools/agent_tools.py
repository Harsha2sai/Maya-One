"""
P31 Tier 2 — Agent coordination tools.
SpawnSubAgent, CheckAgentResult, SendAgentMessage.

These are LLM-callable wrappers around SubAgentManager.
GlobalAgentContainer provides the manager instance.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

VALID_AGENT_TYPES = {"coder", "reviewer", "researcher", "architect", "tester"}


def _get_manager():
    """Lazy import to avoid circular dependency at module load time."""
    from core.runtime.global_agent import GlobalAgentContainer
    return GlobalAgentContainer.get_subagent_manager()


async def spawn_subagent(
    agent_type: str,
    task: str,
    wait: bool = True,
    use_worktree: bool = False,
) -> str:
    """Spawn a specialist subagent to handle a focused task.

    Args:
        agent_type: One of ``coder``, ``reviewer``, ``researcher``,
            ``architect``, ``tester``.
        task: Description of the task for the subagent.
        wait: If True (default), block until the agent completes and return
            its result. If False, return immediately with the agent ID.
        use_worktree: If True, isolate the agent in a git worktree.

    Returns:
        Agent result (if wait=True), agent ID (if wait=False), or error string.
    """
    if agent_type not in VALID_AGENT_TYPES:
        return f"Error: unknown agent_type '{agent_type}'. Valid: {sorted(VALID_AGENT_TYPES)}"

    manager = _get_manager()
    if manager is None:
        return "Error: SubAgentManager not initialized"

    try:
        instance = await manager.spawn(
            agent_type=agent_type,
            task=task,
            wait=wait,
            use_worktree=use_worktree,
        )

        if wait:
            if instance.status.value == "completed":
                return instance.result or "(no output)"
            else:
                return f"Error: agent {instance.status.value} — {instance.error or 'unknown'}"
        else:
            return f"agent_id:{instance.id} status:{instance.status.value}"

    except Exception as e:
        logger.error("spawn_subagent error type=%s: %s", agent_type, e)
        return f"Error: {e}"


async def check_agent_result(agent_id: str) -> str:
    """Check the status and result of a background subagent.

    Args:
        agent_id: The agent ID returned by spawn_subagent with wait=False.

    Returns:
        Status and result string, or error if agent not found.
    """
    manager = _get_manager()
    if manager is None:
        return "Error: SubAgentManager not initialized"

    instance = await manager.check_result(agent_id)
    if instance is None:
        return f"Error: agent '{agent_id}' not found"

    status = instance.status.value
    if status == "completed":
        return f"status:completed\n{instance.result or '(no output)'}"
    elif status == "failed":
        return f"status:failed error:{instance.error or 'unknown'}"
    elif status == "timeout":
        return "status:timeout"
    else:
        return f"status:{status}"


async def send_agent_message(agent_id: str, message: str) -> str:
    """Send a message to a running background subagent.

    Args:
        agent_id: The agent ID to send the message to.
        message: Message content to send.

    Returns:
        Confirmation string or error.
    """
    manager = _get_manager()
    if manager is None:
        return "Error: SubAgentManager not initialized"

    try:
        await manager.send_message(agent_id, message)
        return f"OK: message sent to {agent_id}"
    except KeyError:
        return f"Error: agent '{agent_id}' not found"
    except Exception as e:
        logger.error("send_agent_message error id=%s: %s", agent_id, e)
        return f"Error: {e}"
