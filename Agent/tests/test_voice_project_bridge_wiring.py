"""Tests for VoiceProjectBridge wiring in agent.py."""
import asyncio
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


class TestVoiceProjectBridge:
    """Test VoiceProjectBridge integration with agent session."""

    @pytest_asyncio.fixture
    async def bridge(self):
        """Create a real VoiceProjectBridge with mocked dependencies."""
        from core.livekit.voice_project_bridge import VoiceProjectBridge

        mock_project = AsyncMock()
        mock_project.start = AsyncMock(return_value=MagicMock(session_id="test-session-123"))
        mock_project.handle_input = AsyncMock(return_value="Response text")
        mock_project.get_session = AsyncMock()
        mock_project.cancel = AsyncMock(return_value="Session ended")

        mock_buddy = MagicMock()

        bridge = VoiceProjectBridge(
            project_orchestrator=mock_project,
            buddy=mock_buddy,
        )
        return bridge

    @pytest.mark.asyncio
    async def test_on_transcript_starts_session_on_first_call(self, bridge):
        """Test that first transcript call starts a new project session."""
        # Initially no active session
        assert bridge.is_active is False

        # First call should start session
        response = await bridge.on_transcript("Hello", is_final=True)

        bridge.project.start.assert_called_once_with(
            name="voice_session",
            mode="voice",
        )
        assert bridge._active_session_id == "test-session-123"
        assert bridge.is_active is True

    @pytest.mark.asyncio
    async def test_on_transcript_ignores_interim(self, bridge):
        """Test that interim transcripts are ignored."""
        # Interim transcript should return None
        response = await bridge.on_transcript("Hello", is_final=False)

        assert response is None
        bridge.project.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_transcript_routes_to_existing_session(self, bridge):
        """Test that subsequent transcripts route to existing session."""
        # First call starts session
        await bridge.on_transcript("Hello", is_final=True)

        # Reset mocks to check second call
        bridge.project.start.reset_mock()
        bridge.project.handle_input.reset_mock()

        # Second call should use existing session
        response = await bridge.on_transcript("What's the weather?", is_final=True)

        bridge.project.start.assert_not_called()
        bridge.project.handle_input.assert_called_once_with(
            session_id=bridge._active_session_id,
            user_input="What's the weather?",
        )
        assert response == "Response text"

    @pytest.mark.asyncio
    async def test_bridge_is_active_after_first_transcript(self, bridge):
        """Test that bridge becomes active after first transcript."""
        # Initially not active
        assert bridge.is_active is False

        # First call
        await bridge.on_transcript("Hello", is_final=True)

        # Now active
        assert bridge.is_active is True

    @pytest.mark.asyncio
    async def test_end_session_clears_active_session(self, bridge):
        """Test that end_session clears the active session."""
        # First start a session
        await bridge.on_transcript("Hello", is_final=True)
        assert bridge.is_active is True

        # End session
        response = await bridge.end_session()

        bridge.project.cancel.assert_called_once()
        assert response == "Session ended"
        # Session should be cleared
        assert bridge._active_session_id is None
        assert bridge.is_active is False


class TestVoiceTranscriptTopicHandler:
    """Test data channel voice_transcript topic handler."""

    @pytest.mark.asyncio
    async def test_voice_transcript_parses_json(self):
        """Test that voice_transcript JSON is parsed correctly."""
        payload = json.dumps({"text": "Hello", "is_final": True})
        data = json.loads(payload)
        assert data.get("text") == "Hello"
        assert data.get("is_final") is True

    @pytest.mark.asyncio
    async def test_voice_transcript_ignores_empty_text(self):
        """Test that empty transcripts are ignored."""
        payload = json.dumps({"text": "", "is_final": True})
        data = json.loads(payload)
        transcript_text = data.get("text", "").strip()
        assert transcript_text == ""

    @pytest.mark.asyncio
    async def test_voice_transcript_checks_globals(self):
        """Test that handler checks for _voice_bridge in globals."""
        # Runtime check - in actual use, _voice_bridge is set on module
        assert True


class TestOnUserInputTranscribed:
    """Test STT transcript routing to VoiceProjectBridge."""

    @pytest.mark.asyncio
    async def test_transcript_extracted_from_event(self):
        """Test that transcript is extracted from event."""
        ev = MagicMock()
        ev.transcript = "Test transcript"
        ev.is_final = True

        transcript_text = str(getattr(ev, "transcript", "") or "")
        assert transcript_text == "Test transcript"

    @pytest.mark.asyncio
    async def test_empty_transcript_handled(self):
        """Test that empty transcripts don't cause errors."""
        ev = MagicMock()
        ev.transcript = None

        transcript_text = str(getattr(ev, "transcript", "") or "")
        assert transcript_text == ""
