
import logging
from datetime import datetime
import pytz
from typing import List, Optional, Dict, Any

from core.tasks.task_models import Task, TaskStatus, TaskPriority
from core.tasks.task_store import TaskStore
from core.observability.metrics import metrics
from core.tasks.planning_engine import PlanningEngine

logger = logging.getLogger(__name__)


class _NoopMemoryManager:
    """Fallback memory manager for legacy call sites and tests."""

    def store_task_result(self, **_kwargs):
        return None


class TaskManager:
    """
    Orchestrates the lifecycle of tasks.
    Manages creation, status updates, and retrieval.
    """
    def __init__(self, user_id: str, memory_manager: Any = None):
        self.user_id = user_id
        self.store = TaskStore()
        self.memory = memory_manager if memory_manager is not None else _NoopMemoryManager()
        
    async def create_task_from_request(self, user_request: str) -> Optional[Task]:
        """
        Uses PlanningEngine to plan a task from a natural language request, then creates it.
        """
        logger.info(f"🧠 Planning task for request: {user_request}")
        
        try:
            # 1. Plan with canonical planner schema + repair loop.
            planner = PlanningEngine()
            plan_result = await planner.generate_plan_result(user_request)
            task_steps = plan_result.steps
            if not task_steps:
                logger.error("❌ Planning produced no actionable steps.")
                return None

            # 2. Create Task Object
            new_task = Task(
                user_id=self.user_id,
                title=f"Task: {user_request[:30]}...",
                description=user_request,
                priority=TaskPriority.MEDIUM,
                steps=task_steps,
                status=TaskStatus.PLAN_FAILED if plan_result.plan_failed else TaskStatus.PENDING,
            )
            new_task.metadata = new_task.metadata or {}
            if plan_result.plan_failed and plan_result.error_payload:
                new_task.metadata["planner_error"] = plan_result.error_payload
            
            # 3. Persist
            if await self.store.create_task(new_task):
                await self.store.add_log(new_task.id, f"Task created from request: {user_request}")
                if plan_result.plan_failed and plan_result.error_payload:
                    await self.store.add_log(
                        new_task.id,
                        f"PLAN_FAILED: {plan_result.error_payload}",
                    )
                metrics.increment("tasks_created_total")
                return new_task
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to plan/create task: {e}")
            return None

    async def start_task(self, task_id: str) -> bool:
        """Transition task to RUNNING."""
        task = await self.store.get_task(task_id)
        if not task: return False
        
        if task.status in [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.PLAN_FAILED,
            TaskStatus.STALE,
        ]:
            logger.warning(f"Cannot start task {task_id} in state {task.status}")
            return False
            
        task.status = TaskStatus.RUNNING
        # If starting, ensure we are on step 0 if not set?
        # current_step default is 0.
        
        if await self.store.update_task(task):
            await self.store.add_log(task_id, "Task started")
            return True
        return False

    async def update_progress(self, task_id: str, step_index: int, note: str = None) -> bool:
        """Update current step and add progress note."""
        task = await self.store.get_task(task_id)
        if not task: return False
        
        task.current_step_index = step_index
        if note:
            # Append note to current step result or task logs? 
            # task_models.py Task doesn't have progress_notes list anymore.
            # We'll just log it.
            await self.store.add_log(task_id, f"Progress Step {step_index}: {note}")
        
        # Check if complete?
        if step_index >= len(task.steps):
            # Maybe auto-complete? Or let agent explicitly complete.
            # Let's let explicit completion command handle meaningful closure.
            pass

        if await self.store.update_task(task):
            return True
        return False

    async def complete_task(self, task_id: str, result: str) -> bool:
        """Mark task as COMPLETED."""
        task = await self.store.get_task(task_id)
        if not task: return False
        
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.current_step_index = len(task.steps) # Ensure pointer is at end
        task.metadata = task.metadata or {}
        task.metadata.pop("claimed_by", None)
        task.metadata.pop("lease_expires_at", None)
        task.metadata.pop("last_heartbeat", None)
        
        if await self.store.update_task(task):
            await self.store.add_log(task_id, f"Task completed. Result: {result}")
            metrics.increment("tasks_completed_total")
            
            # Auto-store task result in hybrid memory
            try:
                self.memory.store_task_result(
                    task_id=task_id,
                    result=result,
                    metadata={"task_title": task.title}
                )
            except Exception as e:
                logger.error(f"Failed to store task result in memory: {e}")
            
            # Record runtime
            if task.created_at:
                created = task.created_at
                now = datetime.now(pytz.UTC)
                if created.tzinfo is None:
                    created = created.replace(tzinfo=pytz.UTC)
                
                duration = (now - created).total_seconds()
                logger.debug(f"Task Runtime: {duration} (Type: {type(duration)})")
                metrics.record_histogram("task_runtime_seconds", duration)

            # Record final token usage
            tokens = task.metadata.get("total_tokens", 0)
            logger.debug(f"Task Tokens: {tokens} (Type: {type(tokens)})")
            metrics.record_histogram("task_tokens_total", tokens)
            
            return True
        return False

    async def fail_task(self, task_id: str, error: str) -> bool:
        """Mark task as FAILED."""
        task = await self.store.get_task(task_id)
        if not task: return False
        
        task.status = TaskStatus.FAILED
        task.error = error
        task.metadata = task.metadata or {}
        task.metadata.pop("claimed_by", None)
        task.metadata.pop("lease_expires_at", None)
        task.metadata.pop("last_heartbeat", None)
        
        if await self.store.update_task(task):
            await self.store.add_log(task_id, f"Task failed: {error}")
            metrics.increment("tasks_failed_total")
            return True
        return False

    async def cancel_task(self, task_id: str, reason: str = "User cancelled") -> bool:
        """Mark task as CANCELLED."""
        task = await self.store.get_task(task_id)
        if not task: return False
        
        task.status = TaskStatus.CANCELLED
        task.error = reason # Store reason in error or metadata? Error seems fine for cancellation reason.
        task.metadata = task.metadata or {}
        task.metadata.pop("claimed_by", None)
        task.metadata.pop("lease_expires_at", None)
        task.metadata.pop("last_heartbeat", None)
        
        if await self.store.update_task(task):
            await self.store.add_log(task_id, f"Task cancelled: {reason}")
            return True
        return False

    async def get_active_tasks(self) -> List[Task]:
        """Get all running/pending tasks for this user."""
        return await self.store.get_active_tasks(self.user_id)
    
    async def get_task(self, task_id: str) -> Optional[Task]:
        return await self.store.get_task(task_id)
    
    async def list_history(self, limit: int = 10) -> List[Task]:
        return await self.store.list_tasks(self.user_id, limit=limit)
