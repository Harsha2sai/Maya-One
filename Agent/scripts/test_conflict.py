
import sys
import time
import asyncio

async def main():
    print("Start conflict test...")
    start = time.time()
    
    print("Importing livekit...")
    from livekit import agents
    print(f"Imported livekit in {time.time() - start:.2f}s")
    
    print("Importing chromadb...")
    import chromadb
    print(f"Imported chromadb in {time.time() - start:.2f}s")
    
    print("Done")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
