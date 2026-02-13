import logging
import asyncio
from typing import List, Dict, Any, Optional
from core.system_control.supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    logger.warning("⚠️ sentence-transformers not found. Local embeddings disabled.")

class RAGEngine:
    """
    RAG Engine for semantic search and knowledge retrieval.
    Uses sentence-transformers for local embeddings and Supabase pgvector for storage.
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = None
        if HAS_SENTENCE_TRANSFORMERS:
            try:
                self.model = SentenceTransformer(model_name)
                logger.info(f"🧠 RAG Engine initialized with model: {model_name}")
            except Exception as e:
                logger.error(f"❌ Failed to load model {model_name}: {e}")
        self.db = SupabaseManager()

    def generate_embedding(self, text: str) -> List[float]:
        """Generate vector embedding for text."""
        if not self.model:
            logger.warning("⚠️ Embedding requested but model not loaded. Returning dummy vector.")
            return [0.0] * 384  # Default size for all-MiniLM-L6-v2
        embedding = self.model.encode(text)
        return embedding.tolist()

    async def add_document(self, content: str, metadata: Dict[str, Any] = None) -> bool:
        """Add a document section to the vector store."""
        if not self.db.client:
            return False
            
        embedding = self.generate_embedding(content)
        
        data = {
            "content": content,
            "metadata": metadata or {},
            "embedding": embedding
        }
        
        try:
            result = await asyncio.to_thread(
                lambda: self.db.client.table("document_sections").insert(data).execute()
            )
            return bool(result)
        except Exception as e:
            logger.error(f"❌ Failed to add document to RAG: {e}")
            return False

    async def search(self, query: str, threshold: float = 0.5, count: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant documents using semantic similarity."""
        if not self.db.client:
            return []
            
        query_embedding = self.generate_embedding(query)
        
        try:
            # Call the match_documents RPC function in Supabase
            result = await asyncio.to_thread(
                lambda: self.db.client.rpc("match_documents", {
                    "query_embedding": query_embedding,
                    "match_threshold": threshold,
                    "match_count": count
                }).execute()
            )
            return result.data if hasattr(result, 'data') else []
        except Exception as e:
            logger.error(f"❌ RAG Search Error: {e}")
            return []

    async def get_context(self, query: str) -> str:
        """Helper to get a combined context string for LLM augmentation."""
        results = await self.search(query)
        if not results:
            return ""
            
        context_parts = [r['content'] for r in results]
        return "\n---\n".join(context_parts)

# Singleton instance
_rag_engine = None

def get_rag_engine() -> RAGEngine:
    """Get or initialize the global RAG Engine instance lazily."""
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine()
    return _rag_engine
