
import pytest
from core.context.context_builder import ContextBuilder
from livekit.agents.llm import ChatContext, ChatMessage
from unittest.mock import MagicMock

@pytest.mark.asyncio
async def test_context_under_budget():
    # Mock dependencies
    llm = MagicMock()
    mem_mgr = MagicMock()
    # async return value
    async def mock_get_context(*args, **kwargs):
        return "Memory 1\nMemory 2"
    mem_mgr.get_user_context = mock_get_context
    
    cb = ContextBuilder(llm, mem_mgr, "test_user")
    
    # Create massive history
    massive_history = [
        ChatMessage(role="user", content=[f"Message {i}" * 100])
        for i in range(50)
    ]
    ctx = ChatContext(items=massive_history)
    
    # Build
    msgs, tools = await cb("test", chat_ctx=ctx)
    
    # Verify limit of 6 recent messages + 1 system
    # Should be 7 total
    assert len(msgs) <= 7 
    
    # Verify system prompt contains restricted memory
    sys_msg = msgs[0].content
    if isinstance(sys_msg, list): sys_msg = sys_msg[0]
    
    assert "Memory 1" in sys_msg
    # Ensure it's not huge
    total_tokens_est = sum(len(str(m.content)) for m in msgs) / 4
    print(f"Estimated tokens: {total_tokens_est}")
    assert total_tokens_est < 2000 # Should be well under 4000
    
    print("PASS: Context budget respected")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_context_under_budget())
