
import pytest
from unittest.mock import MagicMock
from core.llm.smart_llm import SmartLLM
from livekit.agents.llm import ChatContext, ChatMessage, ChatChunk, ChoiceDelta
from livekit.agents import llm

@pytest.mark.asyncio
async def test_tools_attached_to_llm_request():
    # Better MockLLM to capture args
    class BetterMockLLM(llm.LLM):
        def __init__(self):
            super().__init__()
            self.last_tools = None
            self.last_choice = None
            # Explicitly set model/provider to strings to avoid MagicMock from __getattr__ if any
            # (though LLM base has them as properties, so it should be fine unless shadowed)
            
        @property
        def model(self): return "test-model"
        
        @property
        def provider(self): return "test-provider"
            
        def chat(self, chat_ctx, tools=None, tool_choice=None, fnc_ctx=None, **kwargs):
            self.last_tools = tools
            self.last_choice = tool_choice
            async def _gen():
                # Yield a simple ChatChunk to satisfy the stream probe
                yield ChatChunk(id="test-id", delta=ChoiceDelta(content="test"))
            return _gen()

    base = BetterMockLLM()
    
    # Mock agent with tools
    agent = MagicMock()
    tool = MagicMock()
    tool.info.name = "open_app"
    agent._tools = [tool]
    
    # Mock context builder
    async def cb(msg, chat_ctx):
        # Must return (messages, tools)
        return [ChatMessage(role="user", content=[msg])], [tool]

    smart = SmartLLM(base_llm=base, context_builder=cb)
    smart.context_builder.agent = agent
    
    # Trigger chat
    ctx = ChatContext(items=[ChatMessage(role="user", content=["open youtube"])])
    stream = smart.chat(chat_ctx=ctx)
    
    # Iterate to trigger the call to base_llm.chat
    async for _ in stream: pass

    assert base.last_tools is not None
    assert len(base.last_tools) == 1
    assert base.last_choice == "auto"
    print("PASS: Tools passed to base LLM")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_tools_attached_to_llm_request())
