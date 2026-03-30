import unittest
from unittest.mock import MagicMock
from core.llm.smart_llm import SmartLLM
import asyncio
from livekit.agents.llm import ChatChunk, ChoiceDelta

class TestToolInjection(unittest.TestCase):
    def test_tools_passed_to_chat(self):
        print("Testing Tool Injection in SmartLLM...")
        
        async def run_test():
            # Mock dependencies
            mock_llm_provider = MagicMock()
            mock_llm_provider.model = "test-model"
            mock_llm_provider.provider = "test-provider"

            async def _empty_stream():
                chunk = ChatChunk(id="test-id", delta=ChoiceDelta(content="ok", tool_calls=[]))
                chunk.usage = None
                yield chunk

            mock_llm_provider.chat = MagicMock(return_value=_empty_stream())
            
            # Custom context builder mock
            async def mock_cb(msg, chat_ctx=None):
                return [], []
            
            tools = [MagicMock()]
            
            smart = SmartLLM(base_llm=mock_llm_provider, context_builder=mock_cb)
            
            mock_ctx = MagicMock()
            
            # 1. Test passing fnc_ctx (LiveKit standard)
            # SmartLLM.chat returns stream synchronously but requires loop for metrics task
            stream = smart.chat(chat_ctx=mock_ctx, fnc_ctx=tools[0])
            
            # Iterate stream to trigger internal calls
            async for _ in stream: pass
            
            # Check if fnc_ctx is normalized into tools=[...]
            args, kwargs = mock_llm_provider.chat.call_args
            
            if kwargs.get('tools') == [tools[0]]:
                print("PASS: Tools injected via fnc_ctx -> tools list")
            else:
                print(f"FAIL: Provider received: {kwargs}")
                raise AssertionError("Tool injection mapping failed")

        # Run in loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()

if __name__ == "__main__":
    unittest.main()
