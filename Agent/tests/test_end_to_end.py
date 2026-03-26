
import pytest
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch
from core.orchestrator.agent_orchestrator import AgentOrchestrator
from core.tasks.task_worker import TaskWorker
from core.tasks.task_models import TaskStatus
from core.tasks.task_steps import TaskStep, WorkerType, TaskStepStatus

@pytest.fixture
def mock_env():
    with patch("core.orchestrator.agent_orchestrator.PlanningEngine") as MockPlanner, \
         patch("core.tasks.workers.base.get_router") as MockRouter, \
         patch("core.tasks.workers.base.ProviderFactory") as MockFactory, \
         patch("core.tasks.workers.base.RoleLLM") as MockRoleLLM, \
         patch("core.tasks.workers.tool_registry.WorkerToolRegistry.is_tool_allowed", return_value=True):
         
        # Setup Planner
        planner = MockPlanner.return_value
        planner.generate_plan = AsyncMock(return_value=[
            TaskStep(description="Step 1", worker="general")
        ])
        
        # Setup Router (for tools)
        router = MockRouter.return_value
        router.tool_executor = AsyncMock(return_value="ToolResult")
        
        # Setup LLM (for reasoning)
        mock_llm = MagicMock()
        async def mock_stream(*args, **kwargs):
             yield MagicMock(choices=[MagicMock(delta=MagicMock(content="ReasoningResult"))])
        mock_llm.chat.return_value = mock_stream()
        MockFactory.get_llm.return_value = mock_llm

        # Ensure worker reasoning path stays deterministic and offline.
        role_llm = MockRoleLLM.return_value
        role_llm.chat = AsyncMock(return_value=mock_stream())
        
        yield planner

@pytest.mark.asyncio
async def test_sanity_check_flow(mock_env):
    planner_mock = mock_env
    
    # 1. Orchestrator creates task
    agent = MagicMock()
    agent.user_id = "test_user_sanity"
    
    # Use real TaskStore logic?
    # TaskStore uses SQLite. For test, we can use real SQLite in memory or tmp file?
    # The default DB URL is sqlite:///./dev_maya_one.db.
    # We should probably mock TaskStore or use a test DB.
    # Tests usually mock store.
    # But TaskWorker instantiates its OWN TaskManager -> TaskStore.
    # If we want them to share state, we must patch TaskStore to behave consistently or use same DB.
    # Let's patch sqlite3 connection or use a shared dict mock?
    # Using a real SQLite file for "Sanity Check" is better but risky if env not set.
    # Let's try to mock TaskStore GLOBALLY.
    
    # Shared State
    tasks_db = {} 
    
    # Mock TaskStore methods to use tasks_db
    # We patch SupabaseTaskStore because TaskStore instantiates it by default if no sqlite env
    with patch.dict(os.environ, {"TASKSTORE_BACKEND": "supabase"}), \
         patch("core.tasks.task_store.SupabaseTaskStore") as MockSupabaseStore:
        # The instance that will be returned by SupabaseTaskStore()
        # This instance becomes self.backend in TaskStore
        backend_instance = MockSupabaseStore.return_value
        
        # Define side effects for the backend instance methods
        async def create_task(task):
            tasks_db[task.id] = task
            return True
        backend_instance.create_task.side_effect = create_task
        
        async def get_active_tasks(user_id):
            return list(tasks_db.values())
        backend_instance.get_active_tasks.side_effect = get_active_tasks
        
        async def update_task(task):
            tasks_db[task.id] = task
            return True
        backend_instance.update_task.side_effect = update_task

        async def get_task(task_id):
            return tasks_db.get(task_id)
        backend_instance.get_task.side_effect = get_task
        
        async def add_log(*args):
             pass
        backend_instance.add_log.side_effect = add_log
        
        # Start Test
        
        # 1. Orchestrator
        orch = AgentOrchestrator(MagicMock(), agent)
        # Verify orchestrator used the mock store (since TaskStore() instantiation uses patched class)
        # Actually TaskStore factory logic selects backend. 
        # We need to patch `TaskStore` class in `agent_orchestrator` and `task_manager`.
        # But `agent_orchestrator` imports `TaskStore` from `core.tasks.task_store`.
        # `task_manager` imports `TaskStore` from `core.tasks.task_store`.
        # `core/tasks/task_worker.py` calls `TaskManager`.
        
        # So check imports.
        # This global patch should work if applied before imports or using patch.object.
        
        # ACT: Create Task
        await orch.handle_message("Create task: do sanity check", user_id="test_user_sanity")
        
        assert len(tasks_db) == 1
        task_id = list(tasks_db.keys())[0]
        task = tasks_db[task_id]
        assert task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}
        assert len(task.steps) == 1
        assert task.steps[0].status == TaskStepStatus.PENDING
        
        # 2. Worker Execution
        worker = TaskWorker(agent.user_id, interval=0)
        # Manually trigger process
        await worker._process_active_tasks()
        
        # ASSERT: Task status updated
        task = tasks_db[task_id]
        # _process_active_tasks calls _execute_next_step
        # _execute_next_step calls worker.execute_step
        # execute_step (General) calls LLM (mocked) matches "ReasoningResult"
        # updates step to DONE
        # task.current_step_index incremented
        
        assert task.steps[0].status == TaskStepStatus.DONE
        assert task.steps[0].result == "ReasoningResult"
        assert task.current_step_index == 1
