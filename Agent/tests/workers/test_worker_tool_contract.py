
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from livekit.agents.llm import ChatContext, ChatMessage
from core.tasks.workers.base import BaseWorker
from core.tasks.task_models import Task
from core.tasks.task_steps import WorkerType, TaskStep

class TestWorkerToolContract(unittest.IsolatedAsyncioTestCase):
    
    async def asyncSetUp(self):
        self.store = MagicMock()
        self.memory = MagicMock()
        self.smart_llm = MagicMock()
        self.user_id = "test_user"
        
        self.worker = BaseWorker(self.user_id, self.store, self.memory, self.smart_llm)
        self.worker.worker_type = WorkerType.RESEARCH
        
        # Mocks for runtime dependencies
        patcher1 = patch("core.tasks.workers.base.WorkerContextBuilder.build")
        self.MockContextBuilder = patcher1.start()
        self.MockContextBuilder.return_value = ChatContext(
            items=[ChatMessage(role="user", content=["test"])]
        )
        
        patcher2 = patch("core.tasks.workers.base.WorkerToolRegistry")
        self.MockRegistry = patcher2.start()
        
        patcher3 = patch("core.tasks.workers.base.RoleLLM")
        self.MockRoleLLM = patcher3.start()
        self.mock_role_llm_instance = MagicMock()
        self.MockRoleLLM.return_value = self.mock_role_llm_instance
        self.mock_role_llm_instance.chat = AsyncMock() # to be configured per test
        
        patcher4 = patch("core.tasks.workers.base.CostGuard")
        patcher4.start()
        
        patcher5 = patch("core.tasks.workers.base.RuntimeMetrics")
        patcher5.start()

        self.addCleanup(patcher1.stop)
        self.addCleanup(patcher2.stop)
        self.addCleanup(patcher3.stop)
        self.addCleanup(patcher4.stop)
        self.addCleanup(patcher5.stop)

    async def test_non_tool_step_enforces_no_tools(self):
        # Step with NO tool assigned
        step = TaskStep(id="s1", description="Think about life", tool=None)
        task = Task(id="t1", user_id="test_user", title="Test", description="Contract test", steps=[step])
        
        # Mock LLM response (empty text)
        mock_stream = AsyncMock()
        mock_stream.__aiter__.return_value = []
        self.mock_role_llm_instance.chat.return_value = mock_stream
        
        await self.worker._execute_reasoning(step, task)
        
        # Verify call to RoleLLM.chat
        call_args = self.mock_role_llm_instance.chat.call_args
        self.assertIsNotNone(call_args)
        kwargs = call_args.kwargs
        
        # MUST have tools=[] and tool_choice="none"
        self.assertEqual(kwargs['tools'], [])
        self.assertEqual(kwargs['tool_choice'], "none")

    async def test_tool_step_allows_tools(self):
        # Step WITH tool assigned
        step = TaskStep(id="s2", description="Search web", tool="web_search")
        task = Task(id="t2", user_id="test_user", title="Test", description="Contract test", steps=[step])
        
        # Mock Registry returning tools
        mock_tool = MagicMock()
        mock_tool.name = "web_search"
        self.MockRegistry.get_tools_for_worker.return_value = [mock_tool]
        
        # Mock LLM response
        mock_stream = AsyncMock()
        mock_stream.__aiter__.return_value = []
        self.mock_role_llm_instance.chat.return_value = mock_stream
        
        await self.worker._execute_reasoning(step, task)
        
        # Verify call
        call_args = self.mock_role_llm_instance.chat.call_args
        kwargs = call_args.kwargs
        
        self.assertEqual(kwargs['tools'], [mock_tool])
        self.assertEqual(kwargs['tool_choice'], "auto")

    async def test_llm_failure_recovery_retries_without_tools(self):
        # Step with tool
        step = TaskStep(id="s3", description="Broken Tool Step", tool="web_search")
        task = Task(id="t3", user_id="test_user", title="Test", description="Contract test", steps=[step])
        
        self.MockRegistry.get_tools_for_worker.return_value = [MagicMock()]
        
        # Setup specific failure on FIRST call
        fail_msg = "Failed to call a function. Please adjust your prompt."
        
        # The mock needs to raise Exception on the await of chat()
        # Side effect: [Exception, SuccessMock]
        
        mock_success_stream = AsyncMock()
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta.content = "Fallback text"
        # Make the async iterator yield the chunk
        async def async_gen():
            yield mock_chunk
        mock_success_stream.__aiter__.side_effect = lambda: async_gen()
        
        # Side effect for chat(): First call raises, second call returns stream
        self.mock_role_llm_instance.chat.side_effect = [
            Exception(fail_msg),
            mock_success_stream
        ]
        
        result = await self.worker._execute_reasoning(step, task)
        
        # Check result contains fallback text
        self.assertIn("Fallback response: Fallback text", result)
        self.assertIn("Note: Tool use failed", result)
        
        # Verify TWO calls to chat
        self.assertEqual(self.mock_role_llm_instance.chat.call_count, 2)
        
        # First call had tools
        args1 = self.mock_role_llm_instance.chat.call_args_list[0].kwargs
        self.assertNotEqual(args1['tools'], [])
        
        # Second call enforced no tools due to retry logic
        args2 = self.mock_role_llm_instance.chat.call_args_list[1].kwargs
        self.assertEqual(args2['tools'], [])
        self.assertEqual(args2['tool_choice'], "none")

if __name__ == "__main__":
    unittest.main()
