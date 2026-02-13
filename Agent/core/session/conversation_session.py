import logging
from typing import Optional, Any
from core.providers.provider_supervisor import ProviderSupervisor
from core.memory import MemoryManager
from core.orchestrator import AgentOrchestrator
from core.providers.provider_health import ProviderState, ProviderHealth
from livekit import agents
from enum import Enum

logger = logging.getLogger(__name__)

class AudioState(Enum):
    HEALTHY = "healthy"
    RECONNECTING = "reconnecting"
    OFFLINE = "offline"

class ConversationSession:
    """
    Persistent session that survives audio transport failures.
    Holds the state of the conversation, memory, and logic as the 'root' object.
    """
    def __init__(
        self,
        user_id: str,
        memory_manager: MemoryManager,
        provider_supervisor: ProviderSupervisor,
    ):
        self.user_id = user_id
        self.memory_manager = memory_manager
        self.provider_supervisor = provider_supervisor
        self.orchestrator: Optional[AgentOrchestrator] = None
        self._current_audio_session: Optional[agents.AgentSession] = None
        
        self.audio_state: AudioState = AudioState.HEALTHY
        
        # Register for health updates
        self.provider_supervisor.add_listener(self._on_provider_health_change)

    def register_orchestrator(self, orchestrator: AgentOrchestrator):
        """Register the orchestrator logic with this session."""
        self.orchestrator = orchestrator

    def _on_provider_health_change(self, name: str, health: ProviderHealth):
        """React to provider health changes (e.g., STT failure)."""
        logger.info(f"🚑 Health update for {name} in conversation {self.user_id}: {health.state}")
        
        # Primary Voice Dependencies
        if name in ["stt_provider", "stt", "deepgram"]:
            if health.state != ProviderState.HEALTHY:
                if self.audio_state != AudioState.RECONNECTING:
                    logger.warning(f"📉 Voice degraded ({name}), switching to RECONNECTING state.")
                    self._set_audio_state(AudioState.RECONNECTING)
                    self._announce("I am having trouble hearing you. Reconnecting voice services...")
            else:
                if self.audio_state == AudioState.RECONNECTING:
                    logger.info(f"📈 Voice service ({name}) restored!")
                    self._set_audio_state(AudioState.HEALTHY)
                    self._announce("Voice connection restored.")

    def _set_audio_state(self, state: AudioState):
        self.audio_state = state
        # TODO: Notify frontend/orchestrator of state change for UI updates

    def _announce(self, message: str):
        """Speak a system message if persistent TTS is available."""
        if self.orchestrator and self.orchestrator.session:
            # We use the orchestrator's current session to speak.
            # However, if TTS itself is broken, this might fail or be silent.
            # But ResilientTTSProxy handles failures gracefully (silent).
            # So this is safe to call.
            import asyncio
            asyncio.create_task(self.orchestrator.session.a_speak(message))

    def attach_audio_session(self, session: agents.AgentSession):
        """Link a new LiveKit audio session to this conversation."""
        logger.info(f"🔗 Attaching new audio session to conversation {self.user_id}")
        self._current_audio_session = session
        
        # Update orchestrator with the new session so it can send audio/replies
        if self.orchestrator:
            self.orchestrator.set_session(session)

    def detach_audio_session(self):
        """Mark the audio session as disconnected/invalid."""
        logger.warning(f"🔌 Audio session detached for conversation {self.user_id}")
        self._current_audio_session = None
        # Orchestrator remains alive, but its session reference is now stale/None
        if self.orchestrator:
            self.orchestrator.set_session(None)

    @property
    def is_audio_connected(self) -> bool:
        return self._current_audio_session is not None
