
import asyncio
import logging
import os
from dotenv import load_dotenv
from core.memory.memory_manager import MemoryManager

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO)

async def test_cloud_sync():
    print("🧪 Testing Cloud Sync Manager...")
    
    # Init manager (auto-starts sync)
    mm = MemoryManager()
    
    # Wait for a few seconds to let the sync loop run
    print("⏳ Waiting for sync loop (5 seconds)...")
    await asyncio.sleep(5)
    
    # Check if task is running
    if mm.cloud_sync._running:
        print("✅ Cloud Sync Manager is running.")
    else:
        print("❌ Cloud Sync Manager is NOT running.")
        
    # Stop cleanup
    await mm.cloud_sync.stop()

if __name__ == "__main__":
    asyncio.run(test_cloud_sync())
