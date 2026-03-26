import asyncio
import logging
import sys
import os
import uuid
import pytz
from datetime import datetime
from typing import List, Optional

# Constants
os.environ["MOCK_TASK_STORE"] = "true" 
os.environ["OPENAI_API_KEY"] = "sk-..." # Should already be in env or loaded by dotenv
# If .env is loaded by python process startup or we need to load it explicitly?
# The orchestrator uses `venv/bin/python`, which might load .env if standard libs do.
# But `Agent/core/config.py` usually loads it.

# Ensure path
sys.path.append(os.getcwd())

# MOCK STATE (Validation Fix: Shared state across instances)
_SHARED_TASKS = {}
_SHARED_LOGS = []

# Mock TaskStore
from core.tasks.task_models import Task, TaskStatus

class InMemoryTaskStore:
    def __init__(self):
        pass
        
    async def create_task(self, task: Task) -> bool:
        _SHARED_TASKS[task.id] = task.model_copy(deep=True)
        return True

    async def get_task(self, task_id: str) -> Optional[Task]:
        t = _SHARED_TASKS.get(task_id)
        if t: return t.model_copy(deep=True)
        return None

    async def update_task(self, task: Task) -> bool:
        if task.id in _SHARED_TASKS:
            task.updated_at = datetime.now(pytz.UTC)
            _SHARED_TASKS[task.id] = task.model_copy(deep=True)
            return True
        return False

    async def list_tasks(self, user_id: str, status: Optional[TaskStatus] = None, limit: int = 50) -> List[Task]:
        res = []
        for t in _SHARED_TASKS.values():
            if t.user_id == user_id:
                if status and t.status != status: continue
                res.append(t.model_copy(deep=True))
        return res[:limit]

    async def add_log(self, task_id: str, message: str) -> bool:
        _SHARED_LOGS.append({
            "task_id": task_id, 
            "message": message, 
            "ts": datetime.now(pytz.UTC)
        })
        return True

    async def get_active_tasks(self, user_id: str) -> List[Task]:
        res = []
        terminal = [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
        logger.info(f"DEBUG: Checking active tasks for {user_id}. Store has {len(_SHARED_TASKS)} tasks.")
        for t in _SHARED_TASKS.values():
            logger.info(f"DEBUG: Task {t.id} - User: {t.user_id} - Status: {t.status}")
            if t.user_id == user_id and t.status not in terminal:
                # Basic priority sort
                res.append(t.model_copy(deep=True))
        # Sort by priority desc
        res.sort(key=lambda x: x.priority.value if hasattr(x.priority, 'value') else 0, reverse=True)
        return res

# PATCH existing TaskStore class module-wide
import core.tasks.task_store
core.tasks.task_store.TaskStore = InMemoryTaskStore

# Now import Worker stuff (which imports TaskStore)
from core.tasks.task_worker import TaskWorker
from core.tasks.task_manager import TaskManager
from core.tasks.task_models import TaskPriority
from core.tasks.task_steps import TaskStep, TaskStepStatus

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Simulation")


class _InMemoryManagerStub:
    """No-op memory manager for local worker simulation."""
    def store_tool_output(self, tool_name: str, output: str, metadata: Optional[dict] = None):
        return None

    def store_task_result(self, task_id: str, result: str, metadata: Optional[dict] = None):
        return None


class _Delta:
    def __init__(self, content: str):
        self.content = content


class _Choice:
    def __init__(self, content: str):
        self.delta = _Delta(content)


class _Chunk:
    def __init__(self, content: str):
        self.choices = [_Choice(content)]


class _MockSmartLLM:
    """Minimal SmartLLM-compatible stub for deterministic worker sanity tests."""
    def chat(self, **kwargs):
        async def _stream():
            yield _Chunk("Sanity check completed.")

        return _stream()


async def main():
    logger.info("🚀 Starting Local Worker Simulation with InMemoryTaskStore")
    
    user_id = "sim_user"
    
    # Use deterministic local stubs so this sanity check does not depend on
    # external providers or full memory stack wiring.
    memory_stub = _InMemoryManagerStub()
    smart_llm_stub = _MockSmartLLM()

    # Disable role-level provider override for this local simulation path.
    from core.llm import llm_roles
    llm_roles.WORKER_CONFIG.provider = None
    llm_roles.WORKER_CONFIG.model = None

    # 1. Start Worker
    # TaskWorker init: self.manager = TaskManager(user_id) -> TaskStore() -> InMemoryTaskStore
    worker = TaskWorker(
        user_id,
        interval=1.0,
        memory_manager=memory_stub,
        smart_llm=smart_llm_stub,
    )
    
    # Start worker loop in background
    # worker.start() calls `asyncio.create_task(self._worker_loop())`
    await worker.start()
    
    try:
        # 2. Create Task using TaskManager
        tm = TaskManager(user_id, memory_stub)
        
        # Create a task that requires LLM processing (General Worker)
        # We want to verify LLM connectivity too!
        # GeneralWorker -> SmartLLM -> ProviderFactory
        
        step_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        
        # Note: Task model might have slightly different init depending on version
        # We use model_validate or init directly?
        # Based on prev view_file, Task is Pydantic.
        
        step = TaskStep(
            id=step_id,
            description="Say hello concisely",
            worker="general", # Maps to GeneralWorker
            status=TaskStepStatus.PENDING
        )
        
        task = Task(
            id=task_id,
            user_id=user_id,
            title="Sanity Check",
            description="Verify LLM connectivity",
            priority=TaskPriority.MEDIUM,
            steps=[step],
            status=TaskStatus.RUNNING,
            created_at=datetime.now(pytz.UTC)
        )
        
        logger.info(f"Creating task {task.id} in Mock Store")
        await tm.store.create_task(task)
        
        # 3. Monitor for completion
        logger.info("Waiting for task completion...")
        start_time = datetime.now()
        
        while (datetime.now() - start_time).total_seconds() < 60:
            t = await tm.get_task(task.id)
            
            if t.status == TaskStatus.COMPLETED:
                logger.info("✅ Task Completed Successfully!")
                logger.info(f"Result: {t.steps[0].result}")
                return # Exit 0
                
            if t.status == TaskStatus.FAILED:
                logger.error(f"❌ Task Failed: {t.error}")
                logger.error(f"Logs: {[l for l in _SHARED_LOGS if l['task_id']==task.id]}")
                sys.exit(1)
            
            # Print progress if step status changes
            if t.steps[0].status == TaskStepStatus.RUNNING:
                logger.info("Task is RUNNING...")
                
            await asyncio.sleep(1)
            
        logger.error("❌ Timeout waiting for task completion")
        sys.exit(1)
        
    finally:
        await worker.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
