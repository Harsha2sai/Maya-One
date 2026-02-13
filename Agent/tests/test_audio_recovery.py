import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from core.session.conversation_session import ConversationSession, AudioState
from core.audio.audio_session_manager import AudioSessionManager
from core.providers.provider_health import ProviderState
from core.providers.provider_supervisor import ProviderSupervisor
from livekit import agents

@pytest.mark.anyio
async def test_audio_state_degradation():
    """Verify ConversationSession reacts to ProviderSupervisor health changes."""
    supervisor = ProviderSupervisor()
    memory_manager = MagicMock()
    conversation = ConversationSession("user-1", memory_manager, supervisor)
    
    # Mock Orchestrator to capture announcements
    mock_orch = MagicMock()
    mock_orch.session = MagicMock()
    mock_orch.session.a_speak = AsyncMock()
    conversation.register_orchestrator(mock_orch)
    
    supervisor.register_provider("stt", MagicMock())
    
    # 1. Simulate Degraded STT
    supervisor.mark_failed("stt", Exception("Connection lost"))
    
    assert conversation.audio_state == AudioState.RECONNECTING
    mock_orch.session.a_speak.assert_called_with("I am having trouble hearing you. Reconnecting voice services...")
    
    # 2. Simulate Restoration
    mock_orch.session.a_speak.reset_mock()
    supervisor.mark_healthy("stt")
    
    assert conversation.audio_state == AudioState.HEALTHY
    mock_orch.session.a_speak.assert_called_with("Voice connection restored.")

@pytest.mark.anyio
async def test_audio_session_manager_restart():
    """Verify AudioSessionManager restarts the session on failure."""
    
    # Mock Dependencies
    mock_ctx = MagicMock(spec=agents.JobContext)
    mock_ctx.room = MagicMock()
    mock_agent = MagicMock()
    mock_conversation = MagicMock(spec=ConversationSession)
    
    # Create a mock session that fails on first start, then succeeds
    mock_session_1 = MagicMock(spec=agents.AgentSession)
    mock_session_1.start = AsyncMock(side_effect=Exception("Simulated Crash"))
    
    mock_session_2 = MagicMock(spec=agents.AgentSession)
    mock_session_2.start = AsyncMock() # Run forever/until cancelled?
    
    async def run_session(*args, **kwargs):
        return # Returns immediately -> graceful exit

    mock_session_2.start.side_effect = run_session

    session_factory = MagicMock(side_effect=[mock_session_1, mock_session_2, mock_session_2])
    
    manager = AudioSessionManager(
        ctx=mock_ctx,
        conversation_session=mock_conversation,
        session_factory=session_factory,
        agent=mock_agent,
        room_input_options=MagicMock()
    )
    
    # Reduce delay for test
    manager._reconnect_delay = 0.01
    
    await manager.run()
    
    # Verify behavior
    assert session_factory.call_count == 2
    
    # First attempt crashed
    mock_conversation.attach_audio_session.assert_any_call(mock_session_1)
    assert mock_conversation.detach_audio_session.call_count >= 1 # Fixed assertion
    
    # Second attempt succeeded
    mock_conversation.attach_audio_session.assert_any_call(mock_session_2)
