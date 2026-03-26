
import logging
from typing import Any, Dict

from core.tasks.task_manager import TaskManager
from core.tasks.task_steps import TaskStep, WorkerType, TaskStepStatus
from core.tasks.task_models import Task

import logging
from typing import Any, Dict
from core.utils.intent_utils import normalize_intent

from core.tasks.task_limits import MAX_DELEGATIONS_PER_TASK
from core.observability.metrics import metrics

async def delegate_work(ctx: Any, worker_type: str, description: str, inputs: Dict[str, Any] = None) -> str:
    """
    Delegate a sub-task to another worker.
    """
    try:
        if not hasattr(ctx, 'task') or not ctx.task:
             return "Error: No active task context found for delegation."

        task: Task = ctx.task
        user_id = ctx.user_id
        
        # 1. Check Delegation Count Limit
        # We can count steps that were created via delegation.
        # But we don't have a flag. Use Task.metadata counter?
        delegation_count = task.metadata.get("delegation_count", 0)
        
        if delegation_count >= MAX_DELEGATIONS_PER_TASK:
             return f"⛔ Delegation limit reached ({MAX_DELEGATIONS_PER_TASK}). Cannot delegate further. Please complete the task yourself."
        
        # 2. Loop Protection
        # Check if identical step exists (same worker, same description)
        for s in task.steps:
            existing_worker_val = normalize_intent(s.worker)
            
            if existing_worker_val.lower() == worker_type.lower() and s.description.strip().lower() == description.strip().lower():
                 return f"⛔ Loop Detected: Step '{description}' for '{worker_type}' already exists. Skipping delegation."

        # Validate worker type
        try:
            target_worker = WorkerType(worker_type.lower())
        except ValueError:
            available_workers = [normalize_intent(w) for w in WorkerType]
            return f"Error: Invalid worker type '{worker_type}'. Available: {available_workers}"
        
        # Create new step
        new_step = TaskStep(
            description=description,
            worker=target_worker,
            parameters=inputs or {},
            status=TaskStepStatus.PENDING
        )
        
        # Incremenet metadata counter
        task.metadata["delegation_count"] = delegation_count + 1
        
        # Insert step AFTER current step
        insertion_index = task.current_step_index + 1
        
        task.steps.insert(insertion_index, new_step)
        
        manager = TaskManager(user_id)
        await manager.store.update_task(task)
        
        metrics.increment("delegations_total")
        worker_str = normalize_intent(target_worker)
        return f"Delegated to {worker_str.upper()}: {description}"

    except Exception as e:
        logger.error(f"Delegation failed: {e}")
        return f"Error delegating work: {str(e)}"
