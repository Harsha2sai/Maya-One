
import asyncio
import logging
import sys
import os

# Add project root to path for direct script execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, AsyncMock
from core.orchestrator.agent_orchestrator import AgentOrchestrator
from core.memory.hybrid_memory_manager import HybridMemoryManager

# Silence external logs
logging.getLogger("livekit").setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

async def run_interactive_agent():
    print("\n" + "="*60)
    print("🤖 MAYA-ONE HYBRID MEMORY INTERACTIVE DEMO")
    print("="*60)
    print("This demo uses the integrated AgentOrchestrator + Hybrid Memory.")
    print("Instructions:")
    print(" 1. Tell Maya something about yourself (e.g., 'I love hiking').")
    print(" 2. Ask something related later to see if she remembers.")
    print(" 3. Type 'stats' to see memory engine statistics.")
    print(" 4. Type 'exit' to quit.\n")

    # Setup Mocks to simulate a running session without LiveKit RTC
    ctx = MagicMock()
    agent = MagicMock()
    agent.user_id = "demo_user"
    
    # We mock the session.a_speak to show what the agent would "say"
    async def mock_speak(message):
        print(f"\n📢 [TTS] {message}")
    
    session = MagicMock()
    session.a_speak = mock_speak
    
    # Initialize Orchestrator (it automatically initializes HybridMemory and Ingestor)
    orchestrator = AgentOrchestrator(ctx, agent, session)
    
    while True:
        try:
            print("\n👤 You: ", end="", flush=True)
            user_input = sys.stdin.readline().strip()
            if not user_input: continue
            if user_input.lower() in ['exit', 'quit']: break
            
            if user_input.lower() == 'stats':
                stats = orchestrator.memory.get_stats()
                print(f"\n🧠 Memory Stats: {stats}")
                continue

            print(f"⚙️  Orchestrator processing intent with memory context...")
            
            # handle_intent will:
            # 1. Retrieve relevant memories
            # 2. Inject them into planning
            # 3. Create a task (mocked behavior for this demo)
            # 4. Auto-store the turn in episodic memory
            
            response = await orchestrator.handle_intent(user_input)
            
            if response:
                print(f"\n🤖 Maya: {response}")
            else:
                print(f"\n🤖 Maya: (Processing task in background...)")

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"❌ Error: {e}", exc_info=True)

if __name__ == "__main__":
    # Ensure environment is loaded for LLM calls during planning
    from dotenv import load_dotenv
    load_dotenv()
    
    try:
        asyncio.run(run_interactive_agent())
    except KeyboardInterrupt:
        pass
