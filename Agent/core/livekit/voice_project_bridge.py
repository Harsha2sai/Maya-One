"""LiveKit voice transcription to ProjectModeOrchestrator bridge."""
from __future__ import annotations

from typing import Optional

from core.project.models import ProjectContext


class VoiceProjectBridge:
    """
    Bridges LiveKit voice transcription to ProjectModeOrchestrator.

    Handles: real-time transcription → project session → PRD generation.
    """

    def __init__(self, project_orchestrator, buddy):
        """
        Initialize the voice project bridge.

        Args:
            project_orchestrator: The ProjectModeOrchestrator instance.
            buddy: The Buddy companion instance.
        """
        self.project = project_orchestrator
        self.buddy = buddy
        self._active_session_id: Optional[str] = None

    async def on_transcript(self, text: str, is_final: bool) -> Optional[str]:
        """
        Called by LiveKit STT on each transcription event.

        Args:
            text: The transcribed text.
            is_final: Whether this is a final transcription (not interim).

        Returns:
            Response from the project orchestrator, or None if ignored.
        """
        if not is_final:
            return None  # ignore interim transcriptions

        if not self._active_session_id:
            # Start new project session on first speech
            session = await self.project.start(
                name="voice_session",
                mode="voice",
            )
            self._active_session_id = session.session_id
            return session

        response = await self.project.handle_input(
            session_id=self._active_session_id,
            user_input=text,
        )
        return response

    async def get_prd(self) -> Optional[str]:
        """
        Get the PRD for the current voice session.

        Returns:
            The PRD as markdown, or None if no active session.
        """
        if not self._active_session_id:
            return None

        session = await self.project.get_session(self._active_session_id)
        if session and session.prd:
            return session.prd.to_markdown()
        return None

    async def end_session(self) -> Optional[str]:
        """
        End the current voice session.

        Returns:
            Confirmation message, or None if no active session.
        """
        if not self._active_session_id:
            return None

        session_id = self._active_session_id
        self._active_session_id = None
        return await self.project.cancel(session_id=session_id)

    @property
    def is_active(self) -> bool:
        """Check if a voice session is active."""
        return self._active_session_id is not None
