import unittest
import os
import asyncio
from core.memory.keyword_store import KeywordStore
from core.memory.hybrid_retriever import HybridRetriever
from core.memory.hybrid_memory_manager import HybridMemoryManager

class TestMemoryKeywords(unittest.TestCase):
    def test_keyword_search_schema(self):
        print("Testing Memory Keyword Search Schema...")
        db_path = "./test_memory_schema.db"
        if os.path.exists(db_path):
            os.remove(db_path)
            
        try:
            # Setup test stores
            ks = KeywordStore(db_path=db_path)
            # We partially mock HybridRetriever by passing our ks
            hr = HybridRetriever(keyword_store=ks)
            
            # Setup manager
            mem = HybridMemoryManager()
            mem.retriever = hr
            
            # Store a memory
            asyncio.run(
                mem.store_conversation_turn("hello", "hi there", metadata={"user_id": "test_user"})
            )
            
            # Now retrieve
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # This triggers: self.retriever.retrieve(query="user:test_user", ...)
            try:
                ctx = loop.run_until_complete(mem.get_user_context("test_user"))
                if ctx:
                    print("PASS: Memory retrieval working")
                else:
                    print("FAIL: No context returned")
            except Exception as e:
                print(f"FAIL: Retrieval raised exception: {e}")
                # We want to see the traceback if it is the SQL error
                raise e
            finally:
                loop.close()

        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

if __name__ == "__main__":
    unittest.main()
