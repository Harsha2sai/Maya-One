
import pytest
import asyncio
from unittest.mock import MagicMock
from core.llm.smart_llm import SmartLLM
from livekit.agents.llm import ChatContext, ChatMessage, ChatChunk, ChoiceDelta
from livekit.agents.llm import FunctionToolCall

# Mock Orchestrator or logic to simulate "Open YouTube" -> Tool Call -> "Opening YouTube" -> DONE.
# This test verifies that we don't get a loop of "Open YouTube" -> "Open YouTube" ...

@pytest.mark.asyncio
async def test_open_youtube_once():
    print("\n--- E2E Test: Open YouTube Once ---")
    
    # 1. Setup Mock LLM that returns a tool call for "open youtube"
    base_llm = MagicMock()
    base_llm.model = "test-model"
    base_llm.provider = "test-provider"
    # We need to simulate the stream of chunks
    # Turn 1: User says "Open YouTube" -> LLM yields ToolCall("open_url", url="youtube.com")
    # Turn 2: Tool Output injected -> LLM yields "I have opened YouTube."
    
    # We can't easily mock the full multi-turn loop here without the Orchestrator.
    # But we can verify SmartLLM's behavior on the first turn.
    
    async def mock_cb(*args, **kwargs):
        tool = MagicMock()
        tool.info.name = "open_url"
        return [], [tool]
        
    llm = SmartLLM(base_llm=base_llm, context_builder=mock_cb)
    llm.base_llm._recent_tools = []
    
    # Simulate LLM outputting the tool call
    async def mock_stream_gen(*args, **kwargs):
        yield ChatChunk(
            id="test-id",
            delta=ChoiceDelta(
                tool_calls=[FunctionToolCall(name="open_url", arguments='{"url": "https://youtube.com"}', call_id="1")]
            )
        )
    
    base_llm.chat.return_value = mock_stream_gen()
    
    # Execute
    ctx = ChatContext(items=[ChatMessage(role="user", content=["Open YouTube"])])
    stream = llm.chat(chat_ctx=ctx)
    
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
        
    # Check that we got the tool call
    assert len(chunks) == 1
    # Check proper nesting: chunk.delta.tool_calls[0].name
    assert chunks[0].delta.tool_calls[0].name == "open_url"
    
    # Check history update
    assert "open_url" in llm._recent_tools
    print("PASS: Single execution and loop guard check")
    # Stream-time loop guard: the same tool emitted 3+ times in one stream should be blocked.
    async def mock_stream_gen_loop(*args, **kwargs):
        for i in range(1, 4):
            yield ChatChunk(
                id=f"test-id-{i}",
                delta=ChoiceDelta(
                    tool_calls=[
                        FunctionToolCall(
                            name="open_url",
                            arguments='{"url": "https://youtube.com"}',
                            call_id=str(i),
                        )
                    ]
                ),
            )

    # Call again with repeated tool calls in a single stream
    base_llm.chat.return_value = mock_stream_gen_loop()
    stream_blocked = llm.chat(chat_ctx=ctx)
    
    blocked_chunks = []
    async for chunk in stream_blocked:
        blocked_chunks.append(chunk)
        
    # Should inject loop warning and limit forwarded tool calls
    assert len(blocked_chunks) > 0

    has_text = any("Blocked repeated call" in (c.delta.content or "") for c in blocked_chunks if c.delta)
    total_tool_calls = sum(
        len(c.delta.tool_calls) for c in blocked_chunks if c.delta and c.delta.tool_calls
    )

    assert has_text
    assert total_tool_calls <= 2
    
    print("PASS: Open YouTube executed once, and loop blocked on repeat.")

if __name__ == "__main__":
    asyncio.run(test_open_youtube_once())
