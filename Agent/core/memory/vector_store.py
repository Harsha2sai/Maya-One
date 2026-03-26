
import logging
import threading
import hashlib
from typing import Any, Dict, List, Optional
# Lazy import for heavy libraries
# import chromadb
# from chromadb.config import Settings
# from sentence_transformers import SentenceTransformer
from core.memory.memory_models import MemoryItem, MemorySource
import os

logger = logging.getLogger(__name__)

class VectorStore:
    """
    ChromaDB-based vector store for semantic memory search.
    Uses sentence-transformers for local embeddings.
    """
    
    def __init__(self, persist_directory: str = None, model_name: str = "all-MiniLM-L6-v2"):
        import chromadb
        from chromadb.config import Settings
        # Lazy import moved to access time
        # from sentence_transformers import SentenceTransformer

        if persist_directory is None:
            persist_directory = os.path.expanduser("~/.maya/memory/chroma")
        
        os.makedirs(persist_directory, exist_ok=True)
        
        self.persist_directory = persist_directory
        self._ephemeral_fallback = False

        try:
            # Initialize ChromaDB client
            self.client = chromadb.PersistentClient(
                path=persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
        except Exception as exc:
            logger.warning(
                "vector_store_persistent_init_failed path=%s error=%s; falling back to ephemeral client",
                persist_directory,
                exc,
            )
            self.client = chromadb.EphemeralClient()
            self._ephemeral_fallback = True
        
        collection_name = "maya_memories"
        if self._ephemeral_fallback:
            path_hash = hashlib.sha1(self.persist_directory.encode("utf-8")).hexdigest()[:12]
            collection_name = f"maya_memories_{path_hash}"

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        # Initialize embedding model lazily
        self._embedding_model = None
        self._model_name = str(model_name or "all-MiniLM-L6-v2").strip() or "all-MiniLM-L6-v2"
        self._model_lock = threading.Lock()
        logger.info(
            "Vector store initialized (embeddings lazy-loaded) fallback_ephemeral=%s",
            self._ephemeral_fallback,
        )

    @property
    def embedding_model(self):
        if self._embedding_model is not None:
            return self._embedding_model
        with self._model_lock:
            if self._embedding_model is None:
                from sentence_transformers import SentenceTransformer
                logger.info("vector_store_model_loading model=%s", self._model_name)
                self._embedding_model = SentenceTransformer(self._model_name)
                logger.info("vector_store_model_ready model=%s", self._model_name)
        return self._embedding_model

    @staticmethod
    def _embedding_to_list(embedding: Any) -> List[float]:
        if hasattr(embedding, "tolist"):
            return embedding.tolist()
        return list(embedding)
    
    def add_memory(self, memory: MemoryItem) -> bool:
        """
        Add a memory item to the vector store.
        """
        try:
            # Generate embedding
            embedding = self._embedding_to_list(self.embedding_model.encode(memory.text))
            
            # Store in ChromaDB
            self.collection.add(
                ids=[memory.id],
                embeddings=[embedding],
                documents=[memory.text],
                metadatas=[{
                    "source": memory.source,
                    "created_at": memory.created_at.isoformat(),
                    **memory.metadata
                }]
            )
            
            logger.debug(f"Added memory {memory.id} to vector store")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add memory to vector store: {e}")
            return False
    
    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic similarity search.
        Returns list of {id, text, metadata, distance} dicts.
        """
        try:
            # Generate query embedding
            query_embedding = self._embedding_to_list(self.embedding_model.encode(query))
            
            # Query ChromaDB
            query_kwargs: Dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": k,
            }
            if filter:
                query_kwargs["where"] = filter
            results = self.collection.query(**query_kwargs)
            
            # Format results
            memories = []
            if results and results['ids'] and len(results['ids']) > 0:
                for i in range(len(results['ids'][0])):
                    memories.append({
                        'id': results['ids'][0][i],
                        'text': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'distance': results['distances'][0][i] if 'distances' in results else None
                    })
            
            logger.debug(f"Vector search returned {len(memories)} results")
            return memories
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        try:
            self.collection.delete(ids=[memory_id])
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False
    
    def count(self) -> int:
        """Return total number of memories."""
        return self.collection.count()
