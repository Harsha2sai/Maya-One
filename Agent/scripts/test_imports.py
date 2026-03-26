
import sys
import os
import time
import asyncio
import logging

sys.path.append(os.getcwd())

logging.basicConfig(level=logging.DEBUG)

async def main():
    print("Start import sequence test...")
    start = time.time()
    
    # Mirroring agent.py imports (simplified)
    print("Importing livekit...")
    from livekit import agents, rtc
    from livekit.agents.llm import ChatContext, ChatMessage
    
    print("Importing core components...")
    from core.governance.types import UserRole
    from core.governance.modes import AgentMode
    from core.utils.intent_utils import normalize_intent
    
    # Mirroring GlobalAgentContainer imports
    print("Importing ToolManager...")
    from core.tools.tool_manager import ToolManager
    
    print("Importing ProviderFactory...")
    from providers.factory import ProviderFactory
    
    print("Importing SQLiteTaskStore...")
    from core.tasks.task_store import SQLiteTaskStore
    
    print("Importing HybridMemoryManager...")
    t0 = time.time()
    from core.memory.hybrid_memory_manager import HybridMemoryManager
    print(f"Imported HybridMemoryManager in {time.time() - t0:.2f}s")
    
    print("Done")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
