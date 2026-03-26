"""
Test real LiveKit AgentSession API to prevent future API drift.

This test verifies that the LiveKit AgentSession has the expected methods
and prevents regressions where deprecated methods are used.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from livekit.agents import AgentSession


def test_agent_session_has_say_method():
    """Verify that AgentSession has the say() method (not a_speak)."""
    
    # Create a mock session that mimics real LiveKit AgentSession
    session = Mock(spec=AgentSession)
    session.say = AsyncMock()
    
    # Verify say() method exists
    assert hasattr(session, 'say'), "AgentSession should have say() method"
    assert callable(session.say), "say() should be callable"
    
    # Verify a_speak() does NOT exist (deprecated)
    assert not hasattr(session, 'a_speak'), "AgentSession should NOT have deprecated a_speak() method"


def test_agent_session_say_is_async():
    """Verify that say() is an async method."""
    
    session = Mock(spec=AgentSession)
    session.say = AsyncMock()
    
    # Verify it's async
    import inspect
    assert inspect.iscoroutinefunction(session.say) or isinstance(session.say, AsyncMock), \
        "say() should be an async method"


@pytest.mark.asyncio
async def test_orchestrator_announce_uses_say():
    """Verify that orchestrator uses say() not a_speak()."""
    
    from core.orchestrator.agent_orchestrator import AgentOrchestrator
    
    # Create mock session
    mock_session = Mock()
    mock_session.say = AsyncMock()
    
    # Create orchestrator with mock session
    mock_ctx = Mock()
    mock_ctx.room = None
    mock_agent = Mock()
    mock_agent.smart_llm = Mock()
    orchestrator = AgentOrchestrator(
        ctx=mock_ctx,
        agent=mock_agent,
        session=mock_session,
        memory_manager=Mock(),
        ingestor=Mock(),
    )
    
    # Call _announce
    await orchestrator._announce("test message")
    
    # Verify say() was called, not a_speak()
    mock_session.say.assert_called_once_with("test message")


@pytest.mark.asyncio
async def test_conversation_session_announce_uses_say():
    """Verify that conversation session uses say() not a_speak()."""
    
    from core.session.conversation_session import ConversationSession
    
    # Create mock orchestrator with session
    mock_session = Mock()
    mock_session.say = AsyncMock()
    
    mock_orchestrator = Mock()
    mock_orchestrator.session = mock_session

    mock_provider_supervisor = Mock()
    mock_provider_supervisor.add_listener = Mock()
    
    # Create conversation session
    conv_session = ConversationSession(
        user_id="test-user",
        memory_manager=Mock(),
        provider_supervisor=mock_provider_supervisor,
    )
    conv_session.orchestrator = mock_orchestrator
    
    # Call _announce
    await conv_session._announce("test message")
    
    # Verify say() was called
    mock_session.say.assert_called_once_with("test message")
