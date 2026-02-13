"""
Local Memory Engine (Mem0)
Handles local-first memory operations using Mem0 with local vector storage (Qdrant).
"""
import logging
import os
from typing import List, Dict, Any, Optional
from mem0 import Memory

logger = logging.getLogger(__name__)

class LocalMemoryEngine:
    def __init__(self, storage_path: str = "./data/memory_qdrant"):
        self.storage_path = storage_path
        os.makedirs(self.storage_path, exist_ok=True)
        
        self.config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "path": self.storage_path,
                    "collection_name": "maya_memory",
                    "embedding_model_dims": 384,
                }
            },
            "embedder": {
                "provider": "huggingface",
                "config": {
                    "model": "sentence-transformers/all-MiniLM-L6-v2"
                }
            },
            "llm": {
                "provider": "groq",
                "config": {
                    "model": "llama-3.1-8b-instant",
                    "temperature": 0,
                    "api_key": os.getenv("GROQ_API_KEY")
                }
            }
        }

        # Validate keys
        if not os.getenv("GROQ_API_KEY"):
            logger.warning("⚠️ GROQ_API_KEY not found! Local Memory might fail.")

        try:
            self.memory = Memory.from_config(self.config)
            logger.info(f"✅ Local Memory Engine initialized at {self.storage_path}")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize Local Memory: {e}")
            self.memory = None

    def add(self, messages: List[Dict[str, str]], user_id: str, metadata: Dict[str, Any] = None) -> bool:
        """Add memories from messages"""
        if not self.memory:
            return False
            
        try:
            self.memory.add(messages, user_id=user_id, metadata=metadata)
            return True
        except Exception as e:
            logger.exception(f"❌ Local Memory add failed: {e}")
            return False

    def search(self, query: str, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search local memories"""
        if not self.memory:
            return []
            
        try:
            results = self.memory.search(query, user_id=user_id, limit=limit)
            return results
        except Exception as e:
            logger.exception(f"❌ Local Memory search failed: {e}")
            return []

    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        """Retrieve all memories for a user"""
        if not self.memory:
            return []
        
        try:
            return self.memory.get_all(user_id=user_id)
        except Exception as e:
            logger.error(f"❌ Local Memory get_all failed: {e}")
            return []

    def clear(self, user_id: str) -> bool:
        """Clear all memories for a user"""
        if not self.memory:
            return False
            
        try:
            self.memory.delete_all(user_id=user_id)
            return True
        except Exception as e:
            logger.error(f"❌ Local Memory clear failed: {e}")
            return False
