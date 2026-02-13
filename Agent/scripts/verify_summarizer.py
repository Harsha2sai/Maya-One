
import asyncio
import logging
import os
from dotenv import load_dotenv
from livekit.agents import ChatContext, ChatMessage
from core.memory.memory_manager import MemoryManager

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO)

async def test_summarizer():
    print("🧪 Testing Memory Summarizer...")
    
    # Ensure keys
    if not os.getenv("GROQ_API_KEY"):
        print("❌ GROQ_API_KEY missing. Skipping test.")
        return

    mm = MemoryManager()
    
    # Create a dummy long conversation
    ctx = ChatContext()
    print("Generating dummy conversation...")
    for i in range(15):
        ctx.add_message(role="user", content=f"User message {i}: I like apples.")
        ctx.add_message(role="assistant", content=f"Assistant message {i}: Apples are good.")
    
    # Trigger summarization (threshold=10)
    print("Triggering summarization (threshold=10)...")
    summary = await mm.summarize_session(ctx, threshold=10)
    
    if summary:
        print(f"✅ Summary generated:\n{summary}")
    else:
        print("❌ No summary generated (check logs).")

if __name__ == "__main__":
    asyncio.run(test_summarizer())
