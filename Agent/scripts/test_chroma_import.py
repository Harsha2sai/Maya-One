
import sys
import time

print("Start import chromadb...")
start = time.time()
try:
    import chromadb
    from chromadb.config import Settings
    print(f"Imported chromadb in {time.time() - start:.2f}s")
    
    print("Initializing client...")
    client = chromadb.PersistentClient(
        path="/home/harsha/.maya/memory/chroma",
        settings=Settings(anonymized_telemetry=False, allow_reset=True)
    )
    print("Client initialized")
except Exception as e:
    print(f"Error: {e}")
