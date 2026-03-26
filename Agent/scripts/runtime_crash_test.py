import asyncio
import os
import subprocess
import time
import sqlite3

DATABASE_URL = "sqlite:///./dev_maya_one.db"
DB_PATH = "dev_maya_one.db"
PYTHONPATH = "."

async def get_task_status(task_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        res = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return res['status'] if res else None

async def get_step_status(task_id, seq):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        res = conn.execute("SELECT status FROM task_steps WHERE task_id = ? AND seq = ?", (task_id, seq)).fetchone()
        return res['status'] if res else None

async def run_crash_test():
    print("🚀 Starting Crash & Resume Test")
    from core.tasks.task_models import Task, TaskStatus
    from core.tasks.task_steps import TaskStep, TaskStepStatus
    from core.tasks.task_store import TaskStore
    
    store = TaskStore()
    
    # 1. Create a multi-step task
    task_id = f"crash-test-{int(time.time())}"
    user_id = "maya_validation_user"
    
    steps = [
        TaskStep(description="Step 1", seq=1, status=TaskStepStatus.PENDING, worker="general"),
        TaskStep(description="Step 2", seq=2, status=TaskStepStatus.PENDING, worker="general"),
        TaskStep(description="Step 3", seq=3, status=TaskStepStatus.PENDING, worker="general")
    ]
    
    task = Task(
        id=task_id,
        user_id=user_id,
        title="Crash Test Task",
        description="A task for testing crash recovery",
        status=TaskStatus.RUNNING,
        steps=steps
    )
    
    await store.create_task(task)
    print(f"✅ Created 3-step task: {task_id}")
    
    # 2. Wait for step 1 to be done
    print("⏳ Waiting for Step 1 to complete...")
    for _ in range(20):
        status = await get_step_status(task_id, 1)
        if status == "done":
            print("✅ Step 1 completed.")
            break
        await asyncio.sleep(1)
    else:
        print("❌ Step 1 timed out.")
        return

    # 3. Kill the worker
    print("💥 Simulating Crash: Killing Worker...")
    subprocess.run(["pkill", "-f", "scripts/start_mock_worker.py"])
    
    # 4. Wait a bit
    await asyncio.sleep(5)
    
    # 5. Restart worker
    print("♻️ Restarting Worker...")
    worker_proc = subprocess.Popen(
        ["export DATABASE_URL=sqlite:///./dev_maya_one.db && export PYTHONPATH=. && export USER_ID=maya_validation_user && .venv/bin/python scripts/start_mock_worker.py"],
        shell=True
    )
    
    # 6. Monitor for task completion
    print("⏳ Waiting for Task completion after resume...")
    for _ in range(30):
        status = await get_task_status(task_id)
        if status == "COMPLETED":
            print("🏆 Crash & Resume Test PASSED!")
            break
        await asyncio.sleep(2)
    else:
        print(f"❌ Task timed out. Current status: {await get_task_status(task_id)}")
    
    # Cleanup: worker is in background now, but we'll let it stay for next tests or kill it manually.

if __name__ == "__main__":
    asyncio.run(run_crash_test())
