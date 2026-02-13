
import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.intelligence.rag_engine import get_rag_engine

async def ingest_files(file_paths: list):
    """Ingest a list of files into the RAG engine."""
    for path in file_paths:
        p = Path(path)
        if not p.exists():
            print(f"⚠️ File not found: {path}")
            continue
            
        print(f"📄 Ingesting {p.name}...")
        with open(p, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Basic chunking (by paragraph or double newline)
        chunks = [c.strip() for c in content.split("\n\n") if c.strip()]
        
        for i, chunk in enumerate(chunks):
            success = await get_rag_engine().add_document(
                content=chunk,
                metadata={"source": p.name, "chunk_index": i}
            )
            if success:
                print(f"  ✅ Added chunk {i+1}/{len(chunks)}")
            else:
                print(f"  ❌ Failed to add chunk {i+1}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingest_docs.py <path_to_file1> <path_to_file2> ...")
        sys.exit(1)
        
    asyncio.run(ingest_files(sys.argv[1:]))
