
import sys
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# Fallback mocking only when livekit is not importable in the test env.
try:
    import livekit  # noqa: F401
except Exception:
    sys.modules["livekit"] = MagicMock()
    sys.modules["livekit.agents"] = MagicMock()
    sys.modules["livekit.agents.llm"] = MagicMock()
    sys.modules["livekit.agents.types"] = MagicMock()
    sys.modules["livekit.plugins"] = MagicMock()
    sys.modules["livekit.rtc"] = MagicMock()
    sys.modules["livekit.agents.pipeline"] = MagicMock()

# Import after mocking
from core.orchestrator.agent_orchestrator import AgentOrchestrator
from core.llm.llm_roles import LLMRole
from core.tasks.planning_engine import PlanningEngine
from core.tasks.workers.base import BaseWorker
from core.tasks.task_steps import TaskStep, WorkerType
from core.response.response_formatter import ResponseFormatter

class TestRoleSeparation(unittest.IsolatedAsyncioTestCase):
    
    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_agent.smart_llm = MagicMock()
        
    async def test_routing_casual_chat(self):
        """Test that casual logic routes to properties _handle_chat_response."""
        context_guard = MagicMock()
        context_guard.count_tokens.return_value = 10  
        memory_manager = MagicMock()
        ctx = MagicMock()
        
        with patch("core.orchestrator.agent_orchestrator.PlanningEngine") as MockPlanningEngine:
            orch = AgentOrchestrator(ctx, self.mock_agent, context_guard=context_guard, memory_manager=memory_manager)
            orch.task_store = AsyncMock()
            orch.task_store.get_active_tasks.return_value = []
            
            # Setup
            orch._handle_chat_response = AsyncMock(return_value=ResponseFormatter.build_response("Chat Response"))
            orch._handle_task_request = AsyncMock()
            
            # Execute
            print("\nExecuting routing casual chat...")
            response = await orch.handle_message("Hello, how are you?", "user123")
            print(f"Response: {response}")
            
            # Verify
            orch._handle_chat_response.assert_called_once()
            orch._handle_task_request.assert_not_called()
            self.assertEqual(response.display_text, "Chat Response")

    async def test_routing_task_request(self):
        """Test that task keywords route to _handle_task_request."""
        context_guard = MagicMock()
        context_guard.count_tokens.return_value = 10 
        memory_manager = MagicMock()
        ctx = MagicMock()
        
        with patch("core.orchestrator.agent_orchestrator.PlanningEngine") as MockPlanningEngine:
            orch = AgentOrchestrator(ctx, self.mock_agent, context_guard=context_guard, memory_manager=memory_manager)
            orch.task_store = AsyncMock()
            orch.task_store.get_active_tasks.return_value = []
            
            # Setup
            orch._handle_chat_response = AsyncMock()
            orch._handle_task_request = AsyncMock(return_value="Task Created")
            orch.agent.smart_llm = None
            
            # Execute
            print("\nExecuting routing task request...")
            response = await orch.handle_message("Create a task to buy groceries", "user123")
            print(f"Response: {response}")
            
            # Verify
            orch._handle_task_request.assert_called_once()
            orch._handle_chat_response.assert_not_called()
            self.assertEqual(response.display_text, "Task Created")

    async def test_routing_multistep_reminder_request(self):
        """Multi-step reminder phrasing should route to planning, not casual chat."""
        context_guard = MagicMock()
        context_guard.count_tokens.return_value = 10
        memory_manager = MagicMock()
        ctx = MagicMock()

        with patch("core.orchestrator.agent_orchestrator.PlanningEngine"):
            orch = AgentOrchestrator(ctx, self.mock_agent, context_guard=context_guard, memory_manager=memory_manager)
            orch.task_store = AsyncMock()
            orch.task_store.get_active_tasks.return_value = []

            orch._handle_chat_response = AsyncMock()
            orch._handle_task_request = AsyncMock(return_value="Task Created")
            orch.agent.smart_llm = None

            response = await orch.handle_message(
                "Set a reminder to check my email in 30 minutes and then open Chrome.",
                "user123",
            )

            orch._handle_task_request.assert_called_once()
            orch._handle_chat_response.assert_not_called()
            self.assertEqual(response.display_text, "Task Created")

    async def test_planner_role_usage(self):
        """Test that PlanningEngine uses PLANNER role and NO tools."""
        mock_llm = MagicMock()
        engine = PlanningEngine(smart_llm=mock_llm)
        
        # Mock RoleLLM inside engine
        engine.role_llm = MagicMock()
        engine.role_llm.chat = AsyncMock(return_value=AsyncMock()) # Mock stream
        
        # Mock ContextBuilder
        with patch("core.context.role_context_builders.planner_context_builder.PlannerContextBuilder.build") as mock_build:
            mock_build.return_value = "Planner Context"
            
            # Execute
            await engine.generate_plan("Research AI")
            
            # Verify
            engine.role_llm.chat.assert_called_once()
            call_args = engine.role_llm.chat.call_args
            assert call_args.kwargs['role'] == LLMRole.PLANNER
            assert call_args.kwargs['tools'] == [] 

    async def test_worker_role_usage(self):
        """Test that BaseWorker uses WORKER role and INJECTS tools."""
        mock_store = MagicMock()
        mock_memory = MagicMock()
        mock_llm = MagicMock()
        
        worker = BaseWorker("user123", mock_store, mock_memory, smart_llm=mock_llm)
        worker.worker_type = WorkerType.RESEARCH 
        
        # Mock RoleLLM construction
        with patch("core.tasks.workers.base.RoleLLM") as MockRoleLLM:
            mock_role_llm_instance = MockRoleLLM.return_value
            mock_role_llm_instance.chat = AsyncMock(return_value=AsyncMock())
            
            # Update: Mock messages attribute on chat_ctx passed to chat
            # RoleLLM checks chat_ctx.messages
            
            # Mock ContextBuilder
            with patch("core.context.role_context_builders.worker_context_builder.WorkerContextBuilder.build") as mock_build:
                mock_ctx = MagicMock()
                mock_ctx.messages = [] # Add messages list attribute
                mock_build.return_value = mock_ctx
                
                # Mock ToolRegistry
                with patch("core.tasks.workers.base.WorkerToolRegistry.get_tools_for_worker") as mock_get_tools:
                    # Return actual objects with .name attribute for validator
                    tool1 = MagicMock()
                    tool1.name = "mock_tool"
                    mock_get_tools.return_value = [tool1]

                    # Execute
                    step = TaskStep(
                        id="1",
                        description="Search web",
                        worker=WorkerType.RESEARCH,
                        tool="mock_tool",
                        parameters={},
                    )
                    task = MagicMock()
                    await worker._execute_reasoning(step, task)
                    
                    # Verify
                    mock_role_llm_instance.chat.assert_called_once()
                    call_args = mock_role_llm_instance.chat.call_args
                    assert call_args.kwargs['role'] == LLMRole.WORKER
                    # Verify tools are passed (not empty)
                    assert len(call_args.kwargs['tools']) > 0

if __name__ == "__main__":
    unittest.main()
