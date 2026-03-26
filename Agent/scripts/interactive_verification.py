
import sys
import os
import asyncio
import logging
from unittest.mock import MagicMock

# Ensure we can import from the Agent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent import Assistant
from livekit.agents import ChatContext
from core.governance.types import UserRole
from core.tools import ToolManager
from core.intent.classifier import IntentResult, IntentType
from unittest.mock import patch
import logging

# Define Mock Tools
async def open_app(ctx, app_name):
    return f"Opened {app_name}"

async def get_weather(ctx, location):
    return f"Weather in {location}"

# Add metadata to mocks
open_app.name = "open_app"
open_app.description = "Opens an application"
open_app.parameters = {"type": "object", "properties": {"app_name": {"type": "string"}}}

get_weather.name = "get_weather"
get_weather.description = "Gets weather"
get_weather.parameters = {"type": "object", "properties": {"location": {"type": "string"}}}

local_tools = [open_app, get_weather]

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

async def run_interactive_session():
    print("--- ZOYA/MAYA Governance Verification ---\n")
    
    # Select Role
    print("Select User Role:")
    print("1. GUEST (Default)")
    print("2. ADMIN")
    choice = input("Enter choice (1/2): ")
    
    role = UserRole.ADMIN if choice == '2' else UserRole.GUEST
    user_id = "admin_user" if role == UserRole.ADMIN else "guest_user"
    
    print(f"\nInitializing Agent as {role.name} ({user_id})...\n")
    
    # Mock dependencies
    mock_room = MagicMock()
    mock_chat_ctx = ChatContext()
    
    # Initialize Agent via ToolManager to verify Governance Logic
    # This sets the global router's executor with governance checks
    agent = await ToolManager.initialize_agent_with_mcp(
        agent_class=Assistant,
        agent_kwargs={
            "chat_ctx": mock_chat_ctx, 
            "room": mock_room,
            "user_role": role,
            "user_id": user_id
        },
        local_tools=local_tools
    )
    
    print("Agent & Governance Layer Ready. Type 'exit' to quit.\n")
    
    while True:
        user_input = input(f"{role.name} > ")
        if user_input.lower() in ['exit', 'quit']:
            break
            
        if not user_input.strip():
            continue
            
        # Simulate Message
        # mock_chat_ctx.messages.append(...) # Skipped to avoid complexity
        
        # We need to simulate the interceptor logic manually or call llm_node
        # But llm_node is an async generator or function depending on implementation.
        # In agent.py, llm_node intercepts and might return a response string or call super.
        
        # For verification, we want to see if it blocks or allows actions.
        # The logic in agent.py:
        # 1. Router.route(last_user_msg)
        # 2. If handled & !needs_llm (fast path) -> returns response
        # 3. If handled & needs_llm -> injects output to chat_ctx
        
        # We can directly call the routing logic to verify governance,
        # mirroring what llm_node does.
        
        from core.routing.router import get_router
        
        print("Thinking...")
        
        # Context injection as per agent.py
        class Context: pass
        ctx = Context()
        ctx.user_role = role
        ctx.user_id = user_id
        
        
        router = get_router()
        
        # Bypass Classifier for direct governance testing
        if user_input.startswith("exec:"):
            tool_name = user_input.split(":", 1)[1].strip()
            print(f"⚡ Forcing execution of: {tool_name}")
            
            # Create a fake intent result
            intent = IntentResult(
                intent_type=IntentType.TOOL_ACTION,
                confidence=1.0,
                matched_tool=tool_name,
                extracted_params={"app_name": "TestApp", "location": "TestLoc"} # Dummy params
            )
            
            # Manually call handle_tool_action to trigger governed executor
            # We need to construct a context object as agent.py does
            ctx = Context()
            ctx.user_role = role
            ctx.user_id = user_id
            
            try:
                # We access the private method or just call the executor directly if exposed
                # But router._handle_tool_action handles param extraction which we skipped
                # So best to call router._handle_tool_action
                result = await router._handle_tool_action(user_input, intent, context=ctx)
                
                if result.error:
                    print(f"❌ BLOCKED/ERROR: {result.error}")
                else:
                    print(f"✅ TOOL EXECUTED: {result.tool_executed}")
                    print(f"   Output: {result.response}")
                    
            except Exception as e:
                print(f"⚠️ Exception during execution: {e}")
                
            print("-" * 20)
            continue

        try:
            result = await router.route(user_input, context=ctx)
            
            if result.handled:
                if result.error:
                    print(f"❌ BLOCKED/ERROR: {result.error}")
                else:
                    if result.tool_executed:
                         print(f"✅ TOOL EXECUTED: {result.tool_executed}")
                         print(f"   Output: {result.response}")
                    else:
                         print(f"ℹ️ HANDLED: {result.response}")
            else:
                 print("💬 (Passed to LLM for chat)")
                 
        except Exception as e:
            print(f"⚠️ Exception: {e}")
            
        print("-" * 20)

if __name__ == "__main__":
    asyncio.run(run_interactive_session())
