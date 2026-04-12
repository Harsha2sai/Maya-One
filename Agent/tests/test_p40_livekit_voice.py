"""Tests for LiveKit voice project bridge (P40)."""
from __future__ import annotations

import pytest

from core.livekit import VoiceProjectBridge


class MockProjectOrchestrator:
    """Mock project orchestrator for testing."""

    def __init__(self):
        self.sessions = {}
        self.session_counter = 0

    async def start(self, name: str, mode: str = "text"):
        """Start a new project session."""
        self.session_counter += 1
        session_id = f"session_{self.session_counter}"
        session = MockSession(session_id=session_id, name=name, mode=mode)
        self.sessions[session_id] = session
        return session

    async def handle_input(self, session_id: str, user_input: str):
        """Handle user input for a session."""
        session = self.sessions.get(session_id)
        if session:
            session.inputs.append(user_input)
            return f"Processed: {user_input}"
        return None

    async def get_session(self, session_id: str):
        """Get a session by ID."""
        return self.sessions.get(session_id)

    async def cancel(self, session_id: str = None):
        """Cancel a session."""
        if session_id and session_id in self.sessions:
            del self.sessions[session_id]
            return f"Session {session_id} cancelled"
        return "No session to cancel"


class MockSession:
    """Mock session for testing."""

    def __init__(self, session_id: str, name: str, mode: str):
        self.session_id = session_id
        self.name = name
        self.mode = mode
        self.inputs = []
        self.prd = None

    def to_markdown(self) -> str:
        """Convert PRD to markdown."""
        if self.prd:
            return f"# {self.name}\n\n{self.prd}"
        return ""


class MockPRD:
    """Mock PRD for testing."""

    def __init__(self, content: str):
        self.content = content

    def to_markdown(self) -> str:
        """Convert PRD to markdown."""
        return self.content


class MockBuddy:
    """Mock buddy for testing."""

    async def on_task_complete(self, success: bool):
        """Handle task completion."""
        pass


@pytest.mark.asyncio
async def test_voice_bridge_creates_session_on_first_final_transcript():
    """Voice bridge creates session on first final transcript."""
    orchestrator = MockProjectOrchestrator()
    buddy = MockBuddy()
    bridge = VoiceProjectBridge(orchestrator, buddy)

    # First final transcript should create session
    response = await bridge.on_transcript("Build a web app", is_final=True)

    assert response is not None
    assert response.session_id == "session_1"
    assert bridge.is_active is True


@pytest.mark.asyncio
async def test_voice_bridge_ignores_interim_transcripts():
    """Voice bridge ignores interim transcripts."""
    orchestrator = MockProjectOrchestrator()
    buddy = MockBuddy()
    bridge = VoiceProjectBridge(orchestrator, buddy)

    # Interim transcript should be ignored
    response = await bridge.on_transcript("Build a", is_final=False)
    assert response is None
    assert bridge.is_active is False


@pytest.mark.asyncio
async def test_voice_bridge_handles_subsequent_transcripts():
    """Voice bridge handles subsequent transcripts after session created."""
    orchestrator = MockProjectOrchestrator()
    buddy = MockBuddy()
    bridge = VoiceProjectBridge(orchestrator, buddy)

    # Create session
    await bridge.on_transcript("Build a web app", is_final=True)

    # Subsequent transcript should be handled
    response = await bridge.on_transcript("With React", is_final=True)
    assert response == "Processed: With React"


@pytest.mark.asyncio
async def test_voice_bridge_get_prd_returns_none_when_no_session():
    """get_prd returns None when no active session."""
    orchestrator = MockProjectOrchestrator()
    buddy = MockBuddy()
    bridge = VoiceProjectBridge(orchestrator, buddy)

    prd = await bridge.get_prd()
    assert prd is None


@pytest.mark.asyncio
async def test_voice_bridge_get_prd_returns_markdown_when_session_has_prd():
    """get_prd returns markdown when session has PRD."""
    orchestrator = MockProjectOrchestrator()
    buddy = MockBuddy()
    bridge = VoiceProjectBridge(orchestrator, buddy)

    # Create session
    await bridge.on_transcript("Build a web app", is_final=True)

    # Add PRD to session
    session = await orchestrator.get_session("session_1")
    session.prd = MockPRD("This is a PRD")

    prd = await bridge.get_prd()
    assert prd is not None
    assert "This is a PRD" in prd


@pytest.mark.asyncio
async def test_voice_bridge_end_session_cancels_active_session():
    """end_session cancels the active session."""
    orchestrator = MockProjectOrchestrator()
    buddy = MockBuddy()
    bridge = VoiceProjectBridge(orchestrator, buddy)

    # Create session
    await bridge.on_transcript("Build a web app", is_final=True)
    assert bridge.is_active is True

    # End session
    response = await bridge.end_session()
    assert response == "Session session_1 cancelled"
    assert bridge.is_active is False


@pytest.mark.asyncio
async def test_voice_bridge_end_session_returns_none_when_no_session():
    """end_session returns None when no active session."""
    orchestrator = MockProjectOrchestrator()
    buddy = MockBuddy()
    bridge = VoiceProjectBridge(orchestrator, buddy)

    response = await bridge.end_session()
    assert response is None


@pytest.mark.asyncio
async def test_voice_bridge_is_active_returns_correct_state():
    """is_active returns correct state based on session."""
    orchestrator = MockProjectOrchestrator()
    buddy = MockBuddy()
    bridge = VoiceProjectBridge(orchestrator, buddy)

    assert bridge.is_active is False

    await bridge.on_transcript("Build a web app", is_final=True)
    assert bridge.is_active is True

    await bridge.end_session()
    assert bridge.is_active is False
