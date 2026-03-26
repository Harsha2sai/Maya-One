
import logging
from typing import List, Optional, Any, Annotated
from livekit.agents import function_tool, RunContext
from core.tasks.task_manager import TaskManager
from core.utils.intent_utils import normalize_intent
from core.tasks.task_models import TaskStatus

logger = logging.getLogger(__name__)

@function_tool(name="create_task")
async def create_task(ctx: RunContext, description: str) -> str:
    """
    Creates a new long-running task based on the description.
    """
    try:
        active_task_id = getattr(ctx.job_context, "task_id", None)
        if active_task_id:
            logger.warning(
                f"⛔ Blocked nested create_task call inside active task execution (task_id={active_task_id})."
            )
            return (
                "Cannot create a nested task while executing another task step. "
                "Continue the current task or finish it first."
            )

        user_id = ctx.job_context.user_id
        from core.runtime.global_agent import GlobalAgentContainer
        manager = TaskManager(user_id, memory_manager=GlobalAgentContainer.get_memory())
        task = await manager.create_task_from_request(description)
        if task:
            status_str = normalize_intent(task.status)
            return f"Task created: {task.title} (ID: {task.id}). Status: {status_str}"
        return "Failed to create task."
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        return f"Error creating task: {str(e)}"

@function_tool(name="list_tasks")
async def list_tasks(ctx: RunContext) -> str:
    """
    Lists all active (non-completed) tasks.
    """
    try:
        user_id = ctx.job_context.user_id
        from core.runtime.global_agent import GlobalAgentContainer
        manager = TaskManager(user_id, memory_manager=GlobalAgentContainer.get_memory())
        tasks = await manager.get_active_tasks()
        if not tasks:
            return "No active tasks."
        
        report = "Active Tasks:\n"
        for t in tasks:
            status_str = normalize_intent(t.status)
            report += f"- [{status_str}] {t.title} (ID: {t.id})\n"
            current_idx = t.current_step_index
            if 0 <= current_idx < len(t.steps):
                step = t.steps[current_idx]
                step_status_str = normalize_intent(step.status)
                report += f"  Current Step: {step.description} ({step_status_str})\n"
        return report
    except Exception as e:
        return f"Error listing tasks: {str(e)}"

@function_tool(name="get_task_status")
async def get_task_status(ctx: RunContext, task_id: str) -> str:
    """
    Get detailed status of a specific task, including all steps.
    """
    try:
        user_id = ctx.job_context.user_id
        from core.runtime.global_agent import GlobalAgentContainer
        manager = TaskManager(user_id, memory_manager=GlobalAgentContainer.get_memory())
        task = await manager.get_task(task_id)
        if not task:
            return f"Task {task_id} not found."
        
        steps_info = []
        for i, step in enumerate(task.steps):
            marker = "▶️" if i == task.current_step_index and task.status == TaskStatus.RUNNING else "  "
            if step.status == "done": marker = "✅"
            if step.status == "failed": marker = "❌"
            
            status_str = normalize_intent(step.status)
            steps_info.append(f"{marker} {i+1}. {step.description} [{status_str}]")
            if step.result:
                steps_info.append(f"      Result: {step.result[:100]}...")
        
        status_str = normalize_intent(task.status)
        return f"Task: {task.title}\nID: {task.id}\nStatus: {status_str}\nDescription: {task.description}\nProgress: {task.current_step_index}/{len(task.steps)}\nSteps:\n" + "\n".join(steps_info)
    except Exception as e:
        return f"Error getting task status: {str(e)}"

@function_tool(name="ask_task_status")
async def ask_task_status(ctx: RunContext, task_id: str) -> str:
    """
    Alias for get_task_status.
    """
    return await get_task_status(ctx, task_id)

@function_tool(name="cancel_task")
async def cancel_task(ctx: RunContext, task_id: str, reason: str = "User request conversation") -> str:
    """
    Cancels a task.
    """
    try:
        user_id = ctx.job_context.user_id
        from core.runtime.global_agent import GlobalAgentContainer
        manager = TaskManager(user_id, memory_manager=GlobalAgentContainer.get_memory())
        success = await manager.cancel_task(task_id, reason)
        if success:
            return f"Task {task_id} cancelled."
        return f"Failed to cancel task {task_id}."
    except Exception as e:
        return f"Error cancelling task: {str(e)}"

def get_task_tools():
    return [create_task, list_tasks, get_task_status, ask_task_status, cancel_task]
