
import logging
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime

from core.tasks.task_models import Task, TaskLog
from core.tasks.task_steps import TaskStep, TaskStepStatus
from core.tasks.task_store import TaskStore
from core.routing.router import get_router
from providers import ProviderFactory
from config.settings import settings
from livekit.agents.llm import ChatContext, ChatMessage

logger = logging.getLogger(__name__)

class StepExecutor:
    """
    Executes individual TaskSteps.
    Handles Tool calls via ExecutionRouter and pure reasoning via LLM.
    """
    def __init__(self, user_id: str, store: TaskStore):
        self.user_id = user_id
        self.store = store
        self.router = get_router()

    async def execute_step(self, task: Task, step: TaskStep) -> bool:
        """
        Execute a single step.
        Returns True if successful, False if failed.
        """
        if step.status == TaskStepStatus.DONE:
            return True
            
        logger.info(f"▶️ Executing Step {step.id}: {step.description} (Tool: {step.tool})")
        
        # 1. Mark Running
        step.status = TaskStepStatus.RUNNING
        await self._update_step_state(task, step)

        try:
            result = None
            
            # 2. Execution Logic
            if step.tool:
                result = await self._execute_tool(step, task)
            else:
                result = await self._execute_reasoning(step, task)
            
            # 3. Handle Result
            step.result = str(result)
            step.status = TaskStepStatus.DONE
            
            await self.store.add_log(task.id, f"Step '{step.description}' completed. Result: {result}")
            await self._update_step_state(task, step)
            return True

        except Exception as e:
            logger.error(f"❌ Step execution failed: {e}")
            step.retry_count += 1
            
            # Simple retry policy (configured here or in settings)
            MAX_RETRIES = 2
            if step.retry_count <= MAX_RETRIES:
                logger.warning(f"🔄 Retrying step {step.id} ({step.retry_count}/{MAX_RETRIES})")
                step.status = TaskStepStatus.PENDING # Reset to pending for next loop
                await self.store.add_log(task.id, f"Step failed, retrying: {e}")
            else:
                step.status = TaskStepStatus.FAILED
                step.result = f"Error: {str(e)}"
                await self.store.add_log(task.id, f"Step failed permanently: {e}")
            
            await self._update_step_state(task, step)
            return False

    async def _execute_tool(self, step: TaskStep, task: Task) -> str:
        """Execute a tool via the Router."""
        if not self.router.tool_executor:
            raise RuntimeError("Tool executor not configured in Router")
            
        tool_name = step.tool
        params = step.parameters or {}
        
        # Create a context object mimicking what router expects
        class ExecutorContext:
            def __init__(self, uid):
                self.user_id = uid
                self.user_role = None # Should fetch real role if possible, defaulting to None/Guest
        
        ctx = ExecutorContext(self.user_id)
        
        # Execute
        # Note: router.tool_executor matches signature (name, params, context)
        return await self.router.tool_executor(tool_name, params, context=ctx)

    async def _execute_reasoning(self, step: TaskStep, task: Task) -> str:
        """Execute a pure reasoning step using LLM."""
        llm = ProviderFactory.get_llm(settings.llm_provider, settings.llm_model)
        
        # Build context
        prompt = f"""
        You are executing a task step.
        Task: {task.title}
        Goal: {task.description}
        
        Current Step: {step.description}
        
        Previous Steps:
        {[f"- {s.description}: {s.result}" for s in task.steps if s.status == TaskStepStatus.DONE]}
        
        Perform this step and provide the result. 
        If it's a thinking step, summarize your thoughts.
        """
        
        ctx = ChatContext(
            [ChatMessage(role="user", content=[prompt])]
        )
        
        response_text = ""
        stream = llm.chat(chat_ctx=ctx)
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    response_text += delta
                    
        return response_text

    async def _update_step_state(self, task: Task, step: TaskStep):
        """Persist step state change."""
        # We need to find the step in the task and update it, then save the task
        # Since 'step' is a reference to the object inside 'task.steps' (if passed correctly),
        # modifying it modifies the task object.
        # But we ensure we save the task.
        
        # Verify reference
        found = False
        for s in task.steps:
            if s.id == step.id:
                # Update fields if it's a copy (Pydantic behavior depends on usage)
                # But here we assume 'step' IS the object from the list.
                s.status = step.status
                s.result = step.result
                s.retry_count = step.retry_count
                found = True
                break
        
        if not found:
             logger.warning("Step object not found in task reference, manual update needed.")
             
        await self.store.update_task(task)
