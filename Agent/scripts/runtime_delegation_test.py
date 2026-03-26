import asyncio
import os
from unittest.mock import MagicMock
from core.tasks.task_models import Task, TaskStatus
from core.tasks.task_steps import TaskStep, TaskStepStatus, WorkerType
from core.tasks.delegation_tools import delegate_work
from core.tasks.task_store import TaskStore

async def test_delegation():
    print("🚀 Starting Delegation Loop Protection Test")
    os.environ["DATABASE_URL"] = "sqlite:///./dev_maya_one.db"
    store = TaskStore()
    user_id = "maya_validation_user"
    
    # Create base task
    task = Task(
        id="delegation-test-task",
        user_id=user_id,
        title="Delegation Test",
        description="Testing loop protection",
        status=TaskStatus.RUNNING
    )
    await store.create_task(task)
    
    # Mock context
    class MockCtx:
        def __init__(self, t, uid):
            self.task = t
            self.user_id = uid

    ctx = MockCtx(task, user_id)
    
    # 1. Test Single Delegation
    print("🔹 Testing single delegation...")
    res = await delegate_work(ctx, "research", "Search for AI news")
    print(f"Result: {res}")
    
    # 2. Test Loop Protection (Same worker, same description)
    print("🔹 Testing loop protection (identical step)...")
    res = await delegate_work(ctx, "research", "Search for AI news")
    print(f"Result: {res}")
    if "Loop Detected" in res:
        print("✅ Loop Protection PASSED (Identical Step detected)")
    else:
        print("❌ Loop Protection FAILED")
        
    # 3. Test Max Delegation Limit (MAX=5)
    print("🔹 Testing max delegation limit...")
    for i in range(10):
        res = await delegate_work(ctx, "general", f"Extra step {i}")
        print(f"Delegation {i}: {res}")
        if "limit reached" in res:
            print(f"✅ Max Delegation Limit PASSED at {i}")
            break
    else:
        print("❌ Max Delegation Limit FAILED")

if __name__ == "__main__":
    asyncio.run(test_delegation())
