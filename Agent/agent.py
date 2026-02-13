import sys
import os
import logging
import asyncio
import uuid
from multiprocessing import Process
from typing import Any, Dict, Optional, List
from dotenv import load_dotenv

# Initialize logging early for startup diagnostics
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# CRITICAL: Apply tool schema patch BEFORE importing tools
# This fixes LiveKit function_tool to generate strict JSON schemas for Groq compatibility
from utils.schema_fixer import apply_schema_patch
apply_schema_patch()

from livekit import agents, rtc
from livekit.agents import AgentSession, RoomInputOptions, ChatContext
from livekit.agents.llm import ChatMessage
from livekit.plugins import noise_cancellation, silero

# Project Imports
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import (
    get_weather, get_time, get_date, get_current_datetime, search_web, 
    send_email, set_alarm, list_alarms, delete_alarm, set_reminder, 
    list_reminders, delete_reminder, create_note, list_notes, read_note, 
    delete_note, create_calendar_event, list_calendar_events, delete_calendar_event,
)
from tools.system.pc_control import open_app, close_app
from api.server import run_token_server
from providers import ProviderFactory
from config.settings import settings
from core.memory import MemoryManager
from core.tools import ToolManager
from core.orchestrator import AgentOrchestrator
from core.routing.router import get_router
from core.governance.types import UserRole
from core.governance.modes import AgentMode
from core.system_control.supabase_manager import SupabaseManager
from core.intelligence.planner import task_planner
from utils.rate_limiter import RateLimiter
from core.llm.smart_llm import SmartLLM
from core.context.context_builder import build_context
from health.startup_checks import run_startup_checks
from core.registry.tool_registry import get_registry

load_dotenv()

class Assistant(agents.Agent):
    def __init__(self, chat_ctx: ChatContext = None, room: rtc.Room = None, user_role: UserRole = UserRole.GUEST, user_id: str = "unknown", mode: AgentMode = AgentMode.SAFE) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            chat_ctx=chat_ctx
        )
        self.room = room
        self.user_role = user_role
        self.user_id = user_id
        self.agent_mode = mode
        self.current_turn_id = None
        self.assistant_response_buffer = ""
        self.rate_limiter = RateLimiter(max_calls=4, period=60) 
        self.planner = task_planner

    async def llm_node(self, chat_ctx: ChatContext, msg: ChatMessage, model_settings: Any, *args, **kwargs):
        """Intercept LLM generation for intent handling and context injection"""
        if not isinstance(msg, ChatMessage):
            return super().llm_node(chat_ctx, msg, model_settings, *args, **kwargs)

        await self.rate_limiter.acquire()

        try:
            last_user_msg = None
            messages = chat_ctx.messages() if callable(chat_ctx.messages) else chat_ctx.messages
            for message in reversed(messages):
                if message.role == "user" and message.content:
                    last_user_msg = message.content
                    if isinstance(last_user_msg, list):
                        last_user_msg = " ".join([str(c) for c in last_user_msg if isinstance(c, str)])
                    break
            
            if last_user_msg:
                # Mode Switching
                if "switch to direct mode" in last_user_msg.lower():
                    self.agent_mode = AgentMode.DIRECT
                    logger.info("⚡ Switched to DIRECT mode")
                    return "I have switched to Direct Mode."
                elif "switch to safe mode" in last_user_msg.lower():
                    self.agent_mode = AgentMode.SAFE
                    logger.info("🛡️ Switched to SAFE mode")
                    return "I have switched back to Safe Mode."

                # Intent Routing
                if self.agent_mode == AgentMode.SAFE:
                    router = get_router()
                else:
                    # Direct Mode fallback
                    router = get_router()
                
                class Context: pass
                ctx = Context()
                ctx.user_role = self.user_role
                ctx.user_id = self.user_id
                ctx.room = self.room
                ctx.turn_id = self.current_turn_id
                
                route_result = await router.route(last_user_msg, context=ctx)
                
                if route_result.handled and not route_result.needs_llm:
                    return route_result.response

                if route_result.handled and route_result.needs_llm:
                    chat_ctx.add_message(
                        role="system", 
                        content=f"Tool Result: {route_result.response}. Phrase this naturally."
                    )
        except Exception as e:
            logger.error(f"⚠️ Error in Assistant.llm_node: {e}")

        if not getattr(self, "_activity", None):
            return self._llm.chat(chat_ctx=chat_ctx)

        return super().llm_node(chat_ctx, msg, model_settings, *args, **kwargs)

async def entrypoint(ctx: agents.JobContext):
    """Orchestrated agent session entrypoint with Audio Autonomy Layer"""
    logger.info("🔌 Initializing session...")
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    
    client_config = AgentOrchestrator.parse_client_config(participant)
    user_id = client_config.get("user_id", participant.identity or "Guest")
    
    # 3. Initialize Resiliency & Conversation Layer
    from core.providers.provider_supervisor import ProviderSupervisor
    from core.session.conversation_session import ConversationSession
    from core.audio.audio_session_manager import AudioSessionManager

    supervisor = ProviderSupervisor()
    await supervisor.start()
    
    memory_manager = MemoryManager()
    
    conversation = ConversationSession(
        user_id=user_id,
        memory_manager=memory_manager,
        provider_supervisor=supervisor
    )

    # 4. Initialize Core Intelligence (Shared across audio sessions)
    llm = ProviderFactory.get_llm(
        client_config.get("llm_provider", settings.llm_provider),
        client_config.get("llm_model", settings.llm_model)
    )

    async def context_builder_wrapper(message: str):
        return await build_context(
            llm=llm,
            memory_manager=memory_manager,
            user_id=user_id,
            message=message,
            tools=[] # Managed by ToolManager later
        )

    smart_llm = SmartLLM(llm, context_builder_wrapper)
    
    chat_ctx = ChatContext()
    ctx.user_id = user_id
    await memory_manager.inject_memories(chat_ctx, user_id)

    role = UserRole.ADMIN if user_id in ["harsha", "harsha2sai", "admin"] else UserRole.GUEST
    
    agent = await ToolManager.initialize_agent_with_mcp(
        agent_class=Assistant,
        agent_kwargs={
            "chat_ctx": chat_ctx, 
            "room": ctx.room,
            "user_role": role,
            "user_id": user_id,
            "mode": AgentMode.SAFE
        },
        local_tools=[] 
    )

    # 5. Initialize Orchestrator (Registered with Conversation)
    orchestrator = AgentOrchestrator(ctx, agent, session=None)
    orchestrator.setup_handlers()
    conversation.register_orchestrator(orchestrator)

    # 6. Define Session Factory (Creates fresh Audio/STT/TTS stack)
    def session_factory() -> AgentSession:
        stt = ProviderFactory.get_stt(
            client_config.get("stt_provider", settings.stt_provider),
            client_config.get("stt_language", settings.stt_language),
            client_config.get("stt_model", settings.stt_model),
            supervisor=supervisor
        )
        tts = ProviderFactory.get_tts(
            client_config.get("tts_provider", settings.tts_provider),
            client_config.get("tts_voice", settings.tts_voice),
            client_config.get("tts_model", settings.tts_model),
            supervisor=supervisor
        )
        
        return AgentSession(
            stt=stt, llm=smart_llm, tts=tts,
            vad=silero.VAD.load(min_silence_duration=1.5),
            tools=[], 
        )

    # 7. Start Audio Autonomy Loop
    
    async def on_connect(session: AgentSession):
        logger.info("👋 Sending initial greeting...")
        await session.generate_reply(instructions=SESSION_INSTRUCTION)

    audio_manager = AudioSessionManager(
        ctx=ctx,
        conversation_session=conversation,
        session_factory=session_factory,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
        on_connect=on_connect
    )

    try:
        await audio_manager.run()

    except Exception as e:
        logger.error(f"⚠️ Top-level session error: {e}")
    finally:
        await supervisor.stop()

async def run_health_checks_task():
    """Startup health checks before worker start"""
    logger.info("🏥 Executing pre-flight health checks...")
    try:
        llm = ProviderFactory.get_llm(settings.llm_provider, settings.llm_model)
        tool_registry = get_registry()
        
        memory_manager = None
        try:
            logger.info("🧠 Initializing Memory Manager...")
            memory_manager = MemoryManager()
        except Exception as e:
            logger.error(f"⚠️ Failed to initialize Memory Manager: {e}")
        
        passed = await run_startup_checks(
            llm_provider=llm,
            tool_registry=tool_registry,
            memory_manager=memory_manager,
            stt_provider_factory=lambda: ProviderFactory.get_stt(settings.stt_provider, settings.stt_language, settings.stt_model),
            tts_provider_factory=lambda: ProviderFactory.get_tts(settings.tts_provider, settings.tts_voice, settings.tts_model)
        )
        
        if not passed:
            logger.error("❌ Pre-flight health checks failed. Aborting.")
            sys.exit(1)
            
        logger.info("✅ Pre-flight health checks passed")
    except Exception as e:
        logger.error(f"❌ Critical error during health checks: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    is_console_mode = "console" in sys.argv
    
    from api.server import async_run_token_server
    if not is_console_mode:
        loop.create_task(async_run_token_server(port=5050))
    
    # Run Health Checks
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # loop.run_until_complete(run_health_checks_task())
    
    # Start Agent
    logger.info("🎤 Starting Worker...")
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
