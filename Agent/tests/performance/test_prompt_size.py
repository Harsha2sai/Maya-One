"""
Test prompt size optimization to ensure token budget stays under 2000.

This test verifies that the ContextBuilder produces prompts within
the target token budget after optimization.
"""

import os
import pytest
from unittest.mock import Mock, AsyncMock
from core.context.context_builder import ContextBuilder, CHAT_MEMORY_TOP_K_DEFAULT
from livekit.agents.llm import ChatContext, ChatMessage


@pytest.mark.asyncio
async def test_prompt_size_under_budget():
    """Verify that constructed context stays under 2000 token budget."""
    
    # Create mock dependencies
    mock_llm = Mock()
    mock_memory_manager = Mock()
    mock_memory_manager.get_user_context = AsyncMock(return_value="Test memory item")
    
    # Create context builder
    builder = ContextBuilder(
        llm=mock_llm,
        memory_manager=mock_memory_manager,
        user_id="test-user",
        rolling_manager=None
    )
    
    # Create mock agent with tools
    mock_agent = Mock()
    mock_agent._tools = [Mock(info=Mock(name=f"tool_{i}")) for i in range(5)]
    builder.set_agent(mock_agent)
    
    # Create chat context with some messages
    chat_ctx = ChatContext()
    chat_ctx.messages = [
        ChatMessage(role="user", content=["Hello"]),
        ChatMessage(role="assistant", content=["Hi there!"]),
        ChatMessage(role="user", content=["How are you?"]),
        ChatMessage(role="assistant", content=["I'm doing well, thanks!"]),
        ChatMessage(role="user", content=["What can you do?"]),
    ]
    
    # Build context
    messages, tools = await builder("Test message", chat_ctx)
    
    # Calculate total token count (estimate: chars / 4)
    total_chars = sum(len(str(m.content)) for m in messages)
    estimated_tokens = total_chars / 4
    
    # Assert token budget
    assert estimated_tokens < 2000, f"Token count {estimated_tokens} exceeds budget of 2000"
    
    # Log for debugging
    print(f"✅ Token count: {estimated_tokens:.0f} (under 2000 budget)")


@pytest.mark.asyncio
async def test_memory_retrieval_limited():
    """Verify that memory retrieval uses the configured chat retrieval k."""
    
    mock_llm = Mock()
    mock_memory_manager = Mock()
    mock_memory_manager.get_user_context = AsyncMock(return_value="Memory line 1\nMemory line 2\nMemory line 3")
    
    builder = ContextBuilder(
        llm=mock_llm,
        memory_manager=mock_memory_manager,
        user_id="test-user"
    )
    
    chat_ctx = ChatContext()
    chat_ctx.messages = [ChatMessage(role="user", content=["Test"])]
    
    await builder("Test", chat_ctx)
    
    expected_k = max(1, int(os.getenv("CHAT_RETRIEVER_K", str(CHAT_MEMORY_TOP_K_DEFAULT))))
    mock_memory_manager.get_user_context.assert_called_once_with("test-user", k=expected_k)


@pytest.mark.asyncio
async def test_conversation_window_limited():
    """Verify that conversation window is limited to 4 messages."""
    
    mock_llm = Mock()
    mock_memory_manager = Mock()
    mock_memory_manager.get_user_context = AsyncMock(return_value=None)
    
    builder = ContextBuilder(
        llm=mock_llm,
        memory_manager=mock_memory_manager,
        user_id="test-user",
        rolling_manager=None
    )
    
    # Create chat context with 10 messages
    chat_ctx = ChatContext()
    chat_ctx.messages = [
        ChatMessage(role="user", content=[f"Message {i}"])
        for i in range(10)
    ]
    
    messages, _ = await builder("Test", chat_ctx)
    
    # Count non-system messages
    non_system = [m for m in messages if m.role != "system"]
    
    # Should be limited to 4
    assert len(non_system) <= 4, f"Conversation window has {len(non_system)} messages, expected <= 4"


@pytest.mark.asyncio
async def test_tool_rules_compressed():
    """Verify that tool usage rules are compressed."""
    
    mock_llm = Mock()
    mock_memory_manager = Mock()
    mock_memory_manager.get_user_context = AsyncMock(return_value=None)
    
    builder = ContextBuilder(
        llm=mock_llm,
        memory_manager=mock_memory_manager,
        user_id="test-user"
    )
    
    chat_ctx = ChatContext()
    chat_ctx.messages = [ChatMessage(role="user", content=["Test"])]
    
    messages, _ = await builder("Test", chat_ctx)
    
    # Get system message
    system_msg = next((m for m in messages if m.role == "system"), None)
    assert system_msg is not None
    
    system_content = str(system_msg.content)
    
    # Verify tool rules section is compressed (should be < 200 chars)
    if "CRITICAL TOOL USAGE" in system_content:
        rules_start = system_content.index("CRITICAL TOOL USAGE")
        rules_section = system_content[rules_start:rules_start+300]
        
        # Count lines in rules section
        rules_lines = rules_section.split('\n')
        assert len(rules_lines) <= 6, f"Tool rules has {len(rules_lines)} lines, expected <= 6"
