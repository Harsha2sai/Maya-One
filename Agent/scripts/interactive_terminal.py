"""
Interactive Console for Phase 0-8 Verification
Allows talking directly to the agent to verify high-level behaviors.
"""
import asyncio
import logging
import sys
from agent import Assistant
from livekit.agents import ChatContext, ChatMessage
from core.governance.modes import AgentMode

# Silence external logs
logging.getLogger("livekit").setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO, format="%(message)s")

async def run_console_interactive():
    print("\n" + "="*50)
    print("🤖 MAYA-ONE PHASE 8 INTERACTIVE VERIFICATION")
    print("="*50)
    print("Commands:")
    print(" - 'direct mode' / 'safe mode' to switch")
    print(" - 'plan: [goal]' to trigger planning")
    print(" - 'research: [topic]' to trigger research agent")
    print(" - 'system: [cmd]' to trigger system operator")
    print(" - 'exit' to quit\n")

    # Load environment
    from dotenv import load_dotenv
    load_dotenv()
    
    # Imports for setup
    from providers import ProviderFactory
    from config.settings import settings
    from core.llm.smart_llm import SmartLLM
    from core.context.context_builder import build_context
    from core.memory import MemoryManager
    from tools import (
        get_weather, search_web, get_current_datetime, send_email,
        set_alarm, list_alarms, create_note, read_note
    )
    from tools.system.pc_control import open_app, close_app
    
    # 1. Setup Dependencies
    llm = ProviderFactory.get_llm(
        settings.llm_provider,
        settings.llm_model
    )
    
    memory_manager = MemoryManager()
    tools_list = [
        get_weather, search_web, get_current_datetime, send_email,
        set_alarm, list_alarms, create_note, read_note, open_app, close_app
    ]
    
    # 2. Setup Context Builder & SmartLLM
    async def context_builder_wrapper(message: str):
        return await build_context(
            llm=llm,
            memory_manager=memory_manager,
            user_id="console_user",
            message=message,
            tools=tools_list
        )
        
    smart_llm = SmartLLM(llm, context_builder_wrapper)
    
    assistant = Assistant()
    assistant._llm = smart_llm # Manually inject LLM for console mode
    
    chat_ctx = ChatContext()
    
    # Add initial greeting context
    chat_ctx.add_message(role="system", content="You are Maya-One, an advanced AI assistant. You have full Phase 8 capabilities enabled including specialized agents, RAG, and self-reflection.")

    while True:
        try:
            print("👤 You: ", end="", flush=True)
            user_input = sys.stdin.readline().strip()
            if not user_input: continue
            if user_input.lower() in ['exit', 'quit']: break
            
            print(f"⚙️  [Mode: {assistant.agent_mode.name}] Processing...")
            
            # Create a message object
            msg = ChatMessage(role="user", content=[user_input])
            
            # Add message to context so agent can see it
            # msg is already a ChatMessage object, but add_message takes role/content
            chat_ctx.add_message(role=msg.role, content=msg.content)
            
            # Execute through Assistant.llm_node (The core routing logic)
            stream = assistant.llm_node(chat_ctx, msg, None)
            
            # Handle sync or async result
            if asyncio.iscoroutine(stream):
                stream = await stream
            
            print("\n🤖 Maya: ", end="", flush=True)
            full_response = ""
            async for chunk in stream:
                 content = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta.content else ""
                 if content:
                     print(content, end="", flush=True)
                     full_response += content
            print("\n")
            
            # Add response to context
            chat_ctx.add_message(role="assistant", content=full_response)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_console_interactive())
