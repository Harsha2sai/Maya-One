import asyncio
import logging
from livekit import agents
from core.response.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)

class AudioSessionManager:
    """
    Manages the Phase 5 audio session, executing the Parallel SLM + Orchestrator LLM flow.
    """
    def __init__(self, session: agents.AgentSession, orchestrator, slm_llm):
        self.session = session
        self.orchestrator = orchestrator
        self.slm_llm = slm_llm
        self.arch_phase = 5
        
    async def run_parallel_flow(self, user_audio_text: str, tool_context=None):
        """
        1. Run SLM ("Let me check...")
        2. In parallel, run full orchestrator response.
        3. Barge-in the SLM with the orchestrator if needed.
        """
        logger.info(f"🎤 [AudioSessionManager] Starting parallel flow for input: {user_audio_text[:50]}...")
        
        slm_task = asyncio.create_task(self._run_slm_acknowledgement(user_audio_text))
        orchestrator_task = asyncio.create_task(
            self.orchestrator.handle_message(
                user_audio_text, user_id=tool_context.user_id, tool_context=tool_context
            )
        )
        
        # We wait for orchestrator to finish. SLM can play while it waits.
        try:
            response = ResponseFormatter.normalize_response(await orchestrator_task)
            
            # If SLM is still speaking its "let me check", we might want to interrupt it 
            # or wait if it's very short. LiveKit automatically interrupts previous say() 
            # if a new say() begins.
            
            # Cancel SLM task if still pending (so it doesn't queue more acknowledgements)
            if not slm_task.done():
                slm_task.cancel()
                
            logger.info("🎤 [AudioSessionManager] Orchestrator finished. Speaking full response.")
            spoken = response.voice_text or response.display_text
            await self.session.say(spoken, allow_interruptions=True, add_to_chat_ctx=True)
            
        except Exception as e:
            logger.error(f"❌ [AudioSessionManager] Orchestrator failed during voice flow: {e}")
            await self.session.say("I hit an internal issue. Please try once more.", allow_interruptions=True)

    async def _run_slm_acknowledgement(self, text: str):
        """Uses a small, fast LLM to generate a quick < 5 token acknowledgement."""
        try:
            # Fake/Fast static responses work too until SLM is fully connected, 
            # but here we would normally call self.slm_llm.chat()
            
            quick_ack = "Let me check that for you." 
            # Hardcoded for speed in prototype Phase 5, or use small model:
            # response = await self.slm_llm.text_chat(f"Reply in 4 words or less acknowledging: {text}")
            
            logger.info(f"⚡ [AudioSessionManager] SLM generated quick ack: {quick_ack}")
            await self.session.say(quick_ack, allow_interruptions=True, add_to_chat_ctx=False)
        except asyncio.CancelledError:
            logger.debug("SLM task cancelled before speaking.")
        except Exception as e:
            logger.warning(f"⚠️ SLM failed: {e}")
