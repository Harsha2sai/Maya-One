import os
import json
import logging
import asyncio
import uuid
from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import AgentSession, RoomInputOptions, ChatContext
from livekit.plugins import noise_cancellation, silero

# Project Imports
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tools import (
    get_weather, get_time, get_date, get_current_datetime, search_web, 
    send_email, set_alarm, list_alarms, delete_alarm, set_reminder, 
    list_reminders, delete_reminder, create_note, list_notes, read_note, 
    delete_note, create_calendar_event, list_calendar_events, delete_calendar_event,
)
from pc_control import open_app, close_app
from api.server import run_token_server
from providers import ProviderFactory
from config.settings import settings
from core.memory import MemoryManager
from core.tools import ToolManager
from core.orchestrator import AgentOrchestrator
from execution_router import get_router

load_dotenv()
logger = logging.getLogger(__name__)

class Assistant(agents.Agent):
    def __init__(self, chat_ctx: ChatContext = None, room: rtc.Room = None) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            chat_ctx=chat_ctx
        )
        self.room = room
        self.current_turn_id = None
        self.assistant_response_buffer = ""

    async def llm_node(self, chat_ctx: ChatContext, *args, **kwargs):
        """Intercept LLM generation for intent handling and context injection"""
        try:
            # 1. Get the last user message for intent classification
            last_user_msg = None
            for msg in reversed(chat_ctx.items):
                if msg.role == "user" and msg.content:
                    last_user_msg = msg.content
                    break
            
            if last_user_msg:
                # 2. Route via Intent Engine
                router = get_router()
                route_result = await router.route(last_user_msg)
                
                # 3. Fast-path: Handle deterministic intents without LLM
                if route_result.handled and not route_result.needs_llm:
                    logger.info(f"⚡ Fast-path execution for intent: {route_result.intent_type}")
                    # Return direct string response - LiveKit translates this to a Speak node
                    return route_result.response

                # 4. Context injection for handled tool results needing phrasing
                if route_result.handled and route_result.needs_llm:
                    logger.info("🛠️ Tool executed, injecting result for LLM phrasing")
                    chat_ctx.add_message(
                        role="system", 
                        content=f"The tool result is: {route_result.response}. Please provide a natural, conversational response based on this."
                    )
        except Exception as e:
            logger.error(f"⚠️ Error in llm_node interception: {e}", exc_info=True)

        return super().llm_node(chat_ctx, *args, **kwargs)

async def entrypoint(ctx: agents.JobContext):
    """Clean agent entrypoint using orchestrated components"""
    logger.info("🔌 Starting orchestrated agent session...")
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    
    # 1. Parse Configuration
    client_config = AgentOrchestrator.parse_client_config(participant)
    user_id = client_config.get("user_id", participant.identity or "Guest")
    
    # 2. Initialize Backend Dependencies (Supabase/Session Track)
    try:
        from supabase_manager import supabase_manager
        if client_config.get("user_id"):
            supabase_manager.create_session_record(
                user_id=client_config["user_id"],
                room_id=ctx.room.name,
                metadata={"agent_type": "orchestrated_v3"}
            )
    except ImportError: pass

    # 3. Resolve Providers & Initialize session
    tools_list = [
        get_weather, search_web, get_current_datetime, send_email,
        set_alarm, list_alarms, delete_alarm, set_reminder, 
        create_note, read_note, create_calendar_event, open_app, close_app
    ]
    
    stt = ProviderFactory.get_stt(
        client_config.get("stt_provider", settings.stt_provider),
        client_config.get("stt_language", settings.stt_language),
        client_config.get("stt_model", settings.stt_model)
    )
    llm = ProviderFactory.get_llm(
        client_config.get("llm_provider", settings.llm_provider),
        client_config.get("llm_model", settings.llm_model)
    )
    tts = ProviderFactory.get_tts(
        client_config.get("tts_provider", settings.tts_provider),
        client_config.get("tts_voice", settings.tts_voice),
        client_config.get("tts_model", settings.tts_model)
    )

    session = AgentSession(
        stt=stt, llm=llm, tts=tts,
        vad=silero.VAD.load(min_silence_duration=1.5),
        tools=tools_list,
    )

    # 4. Context & Tools Setup
    memory_manager = MemoryManager()
    chat_ctx = ChatContext()
    await memory_manager.inject_memories(chat_ctx, user_id)

    agent = await ToolManager.initialize_agent_with_mcp(
        agent_class=Assistant,
        agent_kwargs={"chat_ctx": chat_ctx, "room": ctx.room},
        local_tools=tools_list
    )

    # 5. Connect Orchestrator (Events/Communication)
    orchestrator = AgentOrchestrator(ctx, agent, session)
    orchestrator.setup_handlers()

    # 6. Start Session
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )
    
    await session.generate_reply(instructions=SESSION_INSTRUCTION)

    # 7. Lifecycle Management
    async def _shutdown():
        # Correctly capture the final agent context for memory persistence
        final_ctx = agent.chat_ctx if hasattr(agent, 'chat_ctx') else chat_ctx
        await memory_manager.save_session_context(final_ctx, user_id)
        logger.info("👋 Session cleanup complete")

    ctx.add_shutdown_callback(_shutdown)

if __name__ == "__main__":
    from multiprocessing import Process
    
    # Start Token Server in Background Process
    logger.info("🚀 Starting Integrated Token Server on port 5050...")
    token_server = Process(target=run_token_server, kwargs={"port": 5050}, daemon=True)
    token_server.start()
    
    # Run LiveKit Agent
    logger.info("🎤 Starting LiveKit Agent Worker...")
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
