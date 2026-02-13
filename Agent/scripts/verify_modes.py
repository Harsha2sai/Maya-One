
import asyncio
import logging
from livekit.agents import ChatContext, ChatMessage
from core.governance.modes import AgentMode
from core.governance.types import UserRole

# Mocking LiveKit components for testing
class MockAssistant:
    def __init__(self, mode=AgentMode.SAFE):
        self.agent_mode = mode
        self.user_role = UserRole.ADMIN
        self.user_id = "test_user"
        self.rate_limiter = type('MockRateLimiter', (), {'acquire': asyncio.coroutine(lambda: None)})()

    async def llm_node_logic(self, user_text):
        """Minimal version of the logic in Assistant.llm_node for verification"""
        print(f"\n--- Testing Input: '{user_text}' ---")
        print(f"Current Mode: {self.agent_mode.name}")
        
        # Mode switching logic
        if "switch to direct mode" in user_text.lower():
            self.agent_mode = AgentMode.DIRECT
            return "Switched to Direct Mode"
        elif "switch to safe mode" in user_text.lower():
            self.agent_mode = AgentMode.SAFE
            return "Switched to Safe Mode"

        if self.agent_mode == AgentMode.SAFE:
            print("🛡️ Routing via Heuristic Engine...")
            # Here it would call router.route()
            return "Handled via Safe Mode (Heuristic)"
        else:
            print("⚡ Routing via LLM (Direct Mode)...")
            return "Handled via Direct Mode (LLM)"

async def main():
    assistant = MockAssistant()
    
    # 1. Test Default Mode
    print(await assistant.llm_node_logic("What is the weather?"))
    
    # 2. Test Switch to Direct
    print(await assistant.llm_node_logic("switch to direct mode"))
    
    # 3. Test Direct Mode Execution
    print(await assistant.llm_node_logic("What is the weather?"))
    
    # 4. Test Switch back to Safe
    print(await assistant.llm_node_logic("switch to safe mode"))
    
    # 5. Test Safe Mode Execution
    print(await assistant.llm_node_logic("Set an alarm for 8am"))

if __name__ == "__main__":
    asyncio.run(main())
