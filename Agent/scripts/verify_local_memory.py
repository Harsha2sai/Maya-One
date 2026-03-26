import asyncio
import logging
from core.memory.memory_manager import MemoryManager
from livekit.agents import ChatContext, ChatMessage
from dotenv import load_dotenv

load_dotenv()
import os
print(f"DEBUG: Current WD: {os.getcwd()}")
print(f"DEBUG: OPENAI_API_KEY present: {'YES' if os.getenv('OPENAI_API_KEY') else 'NO'}")
logging.basicConfig(level=logging.INFO)

async def test_local_memory():
    print("Testing Local Memory Manager...")
    mm = MemoryManager()
    
    # Mock Chat Context
    chat_ctx = ChatContext()
    chat_ctx.add_message(role="user", content="My favorite color is blue.")
    chat_ctx.add_message(role="assistant", content="I'll remember that.")
    
    user_id = "test_user_local"
    
    # 1. Save
    print("\n1. Saving Context...")
    await mm.save_session_context(chat_ctx, user_id)
    
    # 2. Retrieve
    print("\n2. Retrieving Context...")
    context = await mm.get_user_context(user_id)
    print(f"Context Found:\n{context}")
    
    if context and "blue" in context:
        print("\n✅ SUCCESS: Memory persisted locally.")
    else:
        print("\n❌ FAILURE: Could not retrieve memory.")

if __name__ == "__main__":
    asyncio.run(test_local_memory())
