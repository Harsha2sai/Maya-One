import logging
import asyncio
import traceback
import contextlib
from typing import Callable, Optional, Any
from livekit import agents
from livekit.agents import AgentSession, RoomInputOptions
from livekit.agents.llm import ChatContext
from core.session.conversation_session import ConversationSession
from core.providers.provider_health import ProviderState
from core.tools.livekit_tool_adapter import adapt_tool_list

# Removed top-level silero import to support lazy loading

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
        from core.runtime.runtime_state import CURRENT_MODE, MayaRuntimeMode
        
        if CURRENT_MODE == MayaRuntimeMode.CONSOLE:
            logger.info("🔇 Audio disabled in console mode")
            return

        self._running = True
        logger.info("🎧 AudioSessionManager starting...")

        while self._running:
            session = None
            try:
                # 1. Create fresh session
                logger.info("🔄 Creating new AgentSession...")
                
                # GUARD: Ensure tools are adapted ONCE and stored
                # This prevents duplicates from multiple adaptations
                if not hasattr(self.agent, '_adapted_tools') or not self.agent._adapted_tools:
                    if hasattr(self.agent, '_tools') and self.agent._tools:
                        self.agent._adapted_tools = adapt_tool_list(self.agent._tools)
                        logger.info(f"🔧 Initially adapted {len(self.agent._adapted_tools)} tools for Audio Session.")
                        
                        # Update internal storage if available (some base classes use this)
                        if hasattr(self.agent, '_tools'):
                             self.agent._tools = self.agent._adapted_tools
                        logger.info(f"🔧 Updated agent._tools with {len(self.agent._adapted_tools)} deduplicated tools")
                    else:
                        self.agent._adapted_tools = []
                        
                safe_tools = self.agent._adapted_tools
                logger.info(f"🛠️ AudioSession: passing {len(safe_tools)} safe tools to session factory")

                # Pass tools to factory
                if CURRENT_MODE == MayaRuntimeMode.CONSOLE:
                    session = None
                else:
                    # FIX: Lazy load silero VAD here if needed, or rely on session_factory
                    session = self.session_factory(tools=safe_tools)
                
                # 2. Attach to conversation logic
                self.conversation_session.attach_audio_session(session)
                
                logger.info("🟢 Starting LiveKit Audio Session...")
                
                # Setup close event waiter
                closed_event = asyncio.Event()
                close_reason = None
                
                def on_close(event):
                    nonlocal close_reason
                    close_reason = event.reason
                    closed_event.set()
                
                session.on("close", on_close)

                if self.on_connect:
                    asyncio.create_task(self._safe_on_connect(session))

                # FAILSAFE: Check if agent thinks it's already running
                if getattr(self.agent, "_activity", None) is not None:
                     existing_activity = self.agent._activity
                     logger.warning(f"⚠️ Agent activity already set to {existing_activity} (Session: {getattr(existing_activity, 'session', 'unknown')}). Forcing clear to allow detailed startup.")
                     self.agent._activity = None

                await session.start(
                    room=self.ctx.room,
                    agent=self.agent,
                    room_input_options=self.room_input_options
                )

                # In normal LiveKit flow start() runs until close.
                # If it returns without a close event, avoid hanging forever.
                if not closed_event.is_set():
                    logger.warning(
                        "⚠️ session.start() returned without close event; treating as graceful shutdown."
                    )
                    break

                # Wait for session close event details.
                await closed_event.wait()
                
                logger.info(f"👋 Audio session ended gracefully (reason: {close_reason}).")
                
                # If closed by user or job shutdown, stop the manager
                if close_reason in (agents.CloseReason.USER_INITIATED, agents.CloseReason.JOB_SHUTDOWN):
                    break
                
                # Otherwise (ERROR, etc), let it loop and restart

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
            finally:
                if session:
                    with contextlib.suppress(Exception):
                        await session.aclose()
                    
                    # Give LiveKit SDK and asyncio loop time to fully deregister the worker
                    await asyncio.sleep(1.0)
                    session = None

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
