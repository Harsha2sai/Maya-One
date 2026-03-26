# scripts/sanity_trigger.py
import asyncio
import sys
import uuid
from core.tasks.task_manager import TaskManager
from core.tasks.task_models import Task, TaskStep, TaskStatus, TaskPriority

async def main():
    try:
        user_id = "preflight_user"
        tm = TaskManager(user_id)
        
        # Create a simple task directly in the store
        # Bypassing LLM planning to ensure deterministic sanity check
        
        task = Task(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title="Sanity Check Task",
            description="A simple 1-step task to verify worker execution",
            priority=TaskPriority.MEDIUM,
            steps=[
                TaskStep(description="Say hello", worker="general") # Assumes 'general' worker handles this or mocks it
            ],
            status=TaskStatus.PENDING
        )
        
        await tm.store.create_task(task)
        print(f"Created task {task.id}")
        
        # Monitor for completion
        # We expect the worker (running separately) to pick this up, mark running, execute step, mark step done, mark task complete.
        
        timeout = 60
        for _ in range(timeout):
            t = await tm.get_task(task.id)
            if not t:
                print("Task disappeared!")
                sys.exit(1)
                
            if t.status == TaskStatus.COMPLETED:
                print("Task completed")
                sys.exit(0)
            
            if t.status == TaskStatus.FAILED:
                print(f"Task failed: {t.error}")
                sys.exit(1)
                
            await asyncio.sleep(1)
            
        print("TIMEOUT awaiting task completion")
        sys.exit(1)

    except Exception as e:
        print(f"Error in sanity_trigger: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
