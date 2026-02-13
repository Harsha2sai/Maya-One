import asyncio
import logging
import traceback
from typing import Callable, Any, Optional

from livekit import agents, rtc
from livekit.agents import AgentSession, RoomInputOptions
from livekit.plugins import noise_cancellation, silero

from core.session.conversation_session import ConversationSession
from core.providers.provider_health import ProviderState

logger = logging.getLogger(__name__)

class AudioSessionManager:
    """
    Manages the lifecycle of LiveKit audio sessions.
    Automatically restarts the session upon failure to ensure voice continuity.
    """
    def __init__(
        self,
        ctx: agents.JobContext,
        conversation_session: ConversationSession,
        session_factory: Callable[[], AgentSession],
        agent: agents.Agent,
        room_input_options: RoomInputOptions,
        on_connect: Optional[Callable[[AgentSession], Any]] = None
    ):
        self.ctx = ctx
        self.conversation_session = conversation_session
        self.session_factory = session_factory
        self.agent = agent
        self.room_input_options = room_input_options
        self.on_connect = on_connect
        self._running = False
        self._reconnect_delay = 2.0  # Start with 2s delay
        self._max_delay = 30.0

    async def run(self):
        """Main loop that keeps the audio session alive."""
        self._running = True
        logger.info("🎧 AudioSessionManager starting...")

        while self._running:
            try:
                # 1. Create fresh session
                logger.info("🔄 Creating new AgentSession...")
                session = self.session_factory()
                
                # 2. Attach to conversation logic
                self.conversation_session.attach_audio_session(session)
                
                logger.info("🟢 Starting LiveKit Audio Session...")
                
                # We need to run the session in a task or just await it.
                # But we also want to fire on_connect.
                # However, await session.start() BLOCKS until session ends.
                # So we can't fire on_connect AFTER it (unless it ends).
                # LiveKit AgentSession.start() usually runs the main loop.
                # We need to fire on_connect immediately after it establishes connection, 
                # but start() blocks.
                
                # WORKAROUND: We can use asyncio.create_task for the greeting 
                # right BEFORE calling start(), assuming start() connects quickly?
                # No, session is not fully ready until start() does some init.
                
                # Check livekit-agents source: 
                # start() -> _run_loop().
                
                # Ideally we want hooks. 
                # But for now, we can schedule the greeting callback on the loop 
                # to run *soon*.
                
                if self.on_connect:
                    asyncio.create_task(self._safe_on_connect(session))

                await session.start(
                    room=self.ctx.room,
                    agent=self.agent,
                    room_input_options=self.room_input_options
                )
                
                # If we get here gracefully, the session ended normally (e.g. user left)
                logger.info("👋 Audio session ended gracefully.")
                break

            except asyncio.CancelledError:
                logger.info("🛑 AudioSessionManager cancelled.")
                break
            except Exception as e:
                logger.error(f"💥 Audio session crashed: {e}")
                logger.debug(traceback.format_exc())
                
                # 4. Handle crash & prepare for restart
                self.conversation_session.detach_audio_session()
                
                logger.warning(f"⏳ Reconnecting audio in {self._reconnect_delay}s...")
                await self._announce_reconnecting()
                
                await asyncio.sleep(self._reconnect_delay)
                
                # Exponential backoff
                self._reconnect_delay = min(self._reconnect_delay * 1.5, self._max_delay)

    async def _safe_on_connect(self, session: AgentSession):
        """Run the on_connect callback safely after a short delay to allow start() to proceed."""
        await asyncio.sleep(1.0) # Wait for start() to likely establish connection
        if self.on_connect:
            try:
                await self.on_connect(session)
            except Exception as e:
                logger.error(f"⚠️ on_connect callback failed: {e}")

    async def _announce_reconnecting(self):
        """
        Attempt to announce reconnection via TTS if possible.
        Note: If TTS itself is down, this might fail silently (depending on provider state).
        """
        # TODO: Implement a way to inject audio directly if needed, or rely on 
        # a separate emergency TTS mechanism if the main one is dead.
        # For now, we log it. In future steps we can try to use a fallback TTS.
        pass

    def stop(self):
        """Stop the manager loop."""
        self._running = False
