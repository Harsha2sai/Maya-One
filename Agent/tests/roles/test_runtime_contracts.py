
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Fallback mocking only when livekit is not importable in the test env.
_mocked_livekit = False
try:
    import livekit  # noqa: F401
except Exception:
    _mocked_livekit = True
    sys.modules["livekit"] = MagicMock()
    sys.modules["livekit.agents"] = MagicMock()
    sys.modules["livekit.agents.llm"] = MagicMock()
    sys.modules["livekit.agents.types"] = MagicMock()

from core.llm.role_llm import RoleLLM
from core.llm.llm_roles import LLMRole, WORKER_CONFIG

if _mocked_livekit:
    # Helper to mock ChatMessage constructor behavior
    def chat_message_side_effect(role, content):
        m = MagicMock()
        m.role = role
        m.content = content
        return m

    sys.modules["livekit.agents.llm"].ChatMessage.side_effect = chat_message_side_effect

class TestRuntimeContracts(unittest.IsolatedAsyncioTestCase):
    
    async def test_token_budget_enforcement(self):
        """Test that RoleLLM truncates excessive context."""
        mock_smart_llm = MagicMock()
        mock_smart_llm.chat = MagicMock(return_value=MagicMock())
        
        role_llm = RoleLLM(smart_llm=mock_smart_llm)
        
        # Create a huge context
        # 1 token approx 4 chars. 
        # Limit is 2000 tokens ~ 8000 chars.
        # Let's create 3 messages: System, Old (huge), New (short).
        
        mock_msg_sys = MagicMock()
        mock_msg_sys.role = "system"
        mock_msg_sys.content = "System Prompt"
        
        mock_msg_huge = MagicMock()
        mock_msg_huge.role = "user"
        mock_msg_huge.content = "A" * 10000 # 2500 tokens
        
        mock_msg_new = MagicMock()
        mock_msg_new.role = "user"
        mock_msg_new.content = "New Request"
        
        mock_ctx = MagicMock()
        mock_ctx.messages = [mock_msg_sys, mock_msg_huge, mock_msg_new]
        
        # Execute
        await role_llm.chat(role=LLMRole.WORKER, chat_ctx=mock_ctx)
        
        # Verify SmartLLM called with truncated messages
        mock_smart_llm.chat.assert_called_once()
        call_args = mock_smart_llm.chat.call_args
        passed_ctx = call_args.kwargs['chat_ctx']
        passed_msgs = passed_ctx.messages
        
        print(f"Passed messages count: {len(passed_msgs)}")
        self.assertGreaterEqual(len(passed_msgs), 2)
        self.assertEqual(passed_msgs[0].role, "system")
        flattened = " ".join(str(getattr(m, "content", "")) for m in passed_msgs)
        self.assertIn("New Request", flattened)

    async def test_system_prompt_deduplication(self):
        """Test that duplicate system prompts are filtered."""
        mock_smart_llm = MagicMock()
        mock_smart_llm.chat = MagicMock(return_value=MagicMock())
        
        role_llm = RoleLLM(smart_llm=mock_smart_llm)
        
        # Context with existing system prompt
        mock_msg_sys_existing = MagicMock()
        mock_msg_sys_existing.role = "system"
        mock_msg_sys_existing.content = "Old System Prompt"
        
        mock_msg_user = MagicMock()
        mock_msg_user.role = "user"
        mock_msg_user.content = "User Msg"
        
        mock_ctx = MagicMock()
        mock_ctx.messages = [mock_msg_sys_existing, mock_msg_user]
        
        # Execute
        await role_llm.chat(role=LLMRole.WORKER, chat_ctx=mock_ctx)
        
        # Verify
        mock_smart_llm.chat.assert_called_once()
        passed_ctx = mock_smart_llm.chat.call_args.kwargs['chat_ctx']
        passed_msgs = passed_ctx.messages
        
        # Expectation: Old system prompt removed. New one injected from Config.
        self.assertEqual(len(passed_msgs), 2)
        self.assertEqual(passed_msgs[0].role, "system")
        system_content = passed_msgs[0].content
        if isinstance(system_content, list):
            system_content = "".join(str(x) for x in system_content)
        self.assertIn("You MUST output valid JSON", str(system_content)) # Worker config has strict prompt
        self.assertNotEqual(str(system_content), "Old System Prompt")

if __name__ == "__main__":
    unittest.main()
