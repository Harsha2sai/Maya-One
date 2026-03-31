import logging
import asyncio
import os
import time
import gc
import threading
from typing import List, Dict, Any
from collections import defaultdict
from core.memory.vector_store import VectorStore
from core.memory.keyword_store import KeywordStore
from core.memory.memory_models import MemoryItem
from core.memory.fts_query_sanitizer import sanitize_fts_query

logger = logging.getLogger(__name__)

class HybridRetriever:
    """
    Hybrid retrieval using Reciprocal Rank Fusion (RRF).
    Combines vector (semantic) and keyword (exact) search results.
    """
    
    def __init__(self, vector_store: VectorStore = None, keyword_store: KeywordStore = None):
        self.vector_store = vector_store or VectorStore()
        self.keyword_store = keyword_store or KeywordStore()
        logger.info("Hybrid retriever initialized")

    def _voice_budget(self, k: int, k_vector: int, k_keyword: int, origin: str) -> tuple[int, int, int]:
        if origin != "voice":
            return k, k_vector, k_keyword

        voice_k = max(1, int(os.getenv("VOICE_RETRIEVER_K", "3")))
        voice_k_vector = max(1, int(os.getenv("VOICE_RETRIEVER_K_VECTOR", "4")))
        voice_k_keyword = max(1, int(os.getenv("VOICE_RETRIEVER_K_KEYWORD", "4")))

        return min(k, voice_k), min(k_vector, voice_k_vector), min(k_keyword, voice_k_keyword)

    def warm_up(self) -> None:
        """
        Pre-load the embedding model to avoid cold-start latency on first voice memory query.
        """
        try:
            _ = self.vector_store.embedding_model
            # Touch collection query path once to prime caches.
            self.vector_store.similarity_search("warmup", k=1)
            logger.info("🧠 retriever_warmed_up")
        except Exception as e:
            logger.warning("🧠 retriever_warmup_failed error=%s", e)

    @staticmethod
    def _filter_by_session(
        results: List[Dict[str, Any]],
        session_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        if not session_id:
            return results
        filtered: List[Dict[str, Any]] = []
        for result in results:
            metadata = result.get("metadata")
            if isinstance(metadata, dict) and metadata.get("session_id") == session_id:
                filtered.append(result)
        return filtered

    def retrieve(
        self,
        query: str,
        k: int = 5,
        k_vector: int = 10,
        k_keyword: int = 10,
        user_id: str | None = None,
        session_id: str | None = None,
        origin: str = "chat",
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories using hybrid RRF approach.
        
        Args:
            query: Search query
            k: Number of final results to return
            k_vector: Number of results to fetch from vector store
            k_keyword: Number of results to fetch from keyword store
        
            user_id: Optional user scope
            session_id: Optional session scope
            origin: ingress origin (`voice` | `chat`)

        Returns:
            List of memory dicts sorted by RRF score
        """
        if origin == "voice" and not user_id:
            logger.warning(
                "🧠 memory_retrieve_no_user_scope query=%s origin=%s",
                (query or "")[:80],
                origin,
            )

        k, k_vector, k_keyword = self._voice_budget(k, k_vector, k_keyword, origin)
        global_search_cap = max(1, int(os.getenv("QDRANT_SEARCH_LIMIT", "5")))
        k_vector = min(k_vector, global_search_cap)
        k_keyword = min(k_keyword, global_search_cap)
        start = time.perf_counter()
        logger.info(
            "🧠 memory_retrieve_start user_id=%s session_id=%s origin=%s k=%s k_vector=%s k_keyword=%s",
            user_id or "none",
            session_id or "none",
            origin,
            k,
            k_vector,
            k_keyword,
        )

        user_filter: dict[str, Any] | None = None
        if user_id and session_id:
            user_filter = {"$and": [{"user_id": user_id}, {"session_id": session_id}]}
        elif user_id:
            user_filter = {"user_id": user_id}
        # Get results from both stores
        try:
            vector_results = self.vector_store.similarity_search(
                query,
                k=k_vector,
                filter=user_filter,
            )
        except Exception as e:
            logger.warning("🧠 vector_retrieval_failed query=%s error=%s", (query or "")[:80], e)
            vector_results = []

        safe_query = sanitize_fts_query(query)
        if safe_query:
            try:
                keyword_results = self.keyword_store.keyword_search(
                    safe_query,
                    k=k_keyword,
                    user_id=user_id,
                    session_id=session_id,
                )
            except Exception as e:
                logger.warning("🧠 keyword_retrieval_failed query=%s error=%s", (query or "")[:80], e)
                keyword_results = []
        else:
            logger.info("🧠 keyword_retrieval_skipped reason=sanitized_query_empty")
            keyword_results = []

        vector_results = self._filter_by_session(vector_results, session_id=session_id)
        keyword_results = self._filter_by_session(keyword_results, session_id=session_id)

        logger.debug(f"Vector: {len(vector_results)}, Keyword: {len(keyword_results)} results")
        
        # Apply Reciprocal Rank Fusion
        rrf_scores = self._reciprocal_rank_fusion(vector_results, keyword_results)
        
        # Sort by RRF score and return top k
        sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:k]
        
        # Build final result list with full memory data
        final_results = []
        memory_map: Dict[str, Dict[str, Any]] = {}
        for memory in vector_results:
            memory_map[memory["id"]] = memory
        for memory in keyword_results:
            memory_map[memory["id"]] = memory
        
        for memory_id, score in sorted_results:
            if memory_id in memory_map:
                memory = memory_map[memory_id].copy()
                memory['rrf_score'] = score
                final_results.append(memory)

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        logger.info(f"Hybrid retrieval returned {len(final_results)} memories")
        logger.info(
            "🧠 memory_retrieve_results count=%s vector_hits=%s keyword_hits=%s fused=%s",
            len(final_results),
            len(vector_results),
            len(keyword_results),
            len(sorted_results),
        )
        logger.info("🧠 memory_retrieve_ms=%.2f", elapsed_ms)
        del memory_map
        del sorted_results
        if len(vector_results) + len(keyword_results) > 8:
            gc.collect()
        return final_results

    async def retrieve_async(
        self,
        query: str,
        k: int = 5,
        k_vector: int = 10,
        k_keyword: int = 10,
        user_id: str | None = None,
        session_id: str | None = None,
        origin: str = "chat",
    ) -> List[Dict[str, Any]]:
        voice_timeout_s = max(0.1, float(os.getenv("VOICE_RETRIEVER_TIMEOUT_S", "0.60")))
        chat_timeout_s = max(0.2, float(os.getenv("RETRIEVER_TIMEOUT_S", "2.0")))
        timeout_s = voice_timeout_s if origin == "voice" else chat_timeout_s
        done = threading.Event()
        state: Dict[str, Any] = {"result": None, "error": None}

        def _worker() -> None:
            try:
                state["result"] = self.retrieve(
                    query,
                    k,
                    k_vector,
                    k_keyword,
                    user_id,
                    session_id,
                    origin,
                )
            except Exception as exc:
                state["error"] = exc
            finally:
                done.set()

        threading.Thread(target=_worker, daemon=True).start()
        try:
            start = time.perf_counter()
            while not done.is_set():
                if (time.perf_counter() - start) >= timeout_s:
                    raise asyncio.TimeoutError
                await asyncio.sleep(0.01)

            if state["error"] is not None:
                raise state["error"]
            return state["result"] or []
        except asyncio.TimeoutError:
            logger.warning(
                "🧠 retriever_timeout timeout_s=%.2f origin=%s query=%s",
                timeout_s,
                origin,
                (query or "")[:80],
            )
            return []
        except Exception as e:
            logger.error(
                "🧠 retriever_error origin=%s query=%s error=%s",
                origin,
                (query or "")[:80],
                e,
            )
            return []

    async def retrieve_with_scope_fallback(
        self,
        query: str,
        user_id: str | None,
        session_id: str | None,
        origin: str,
        k: int = 5,
        k_vector: int = 10,
        k_keyword: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve with scope fallback:
        1) user+session scope
        2) user-only scope when session-scoped query returns empty
        """
        if user_id and session_id:
            scoped_results = await self.retrieve_async(
                query=query,
                k=k,
                k_vector=k_vector,
                k_keyword=k_keyword,
                user_id=user_id,
                session_id=session_id,
                origin=origin,
            )
            if scoped_results:
                return scoped_results

            logger.info(
                "🧠 retriever_scope_fallback reason=session_scoped_empty user_id=%s session_id=%s origin=%s",
                user_id,
                session_id,
                origin,
            )

        return await self.retrieve_async(
            query=query,
            k=k,
            k_vector=k_vector,
            k_keyword=k_keyword,
            user_id=user_id,
            session_id=None,
            origin=origin,
        )
    
    def _reciprocal_rank_fusion(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        k: int = 60
    ) -> Dict[str, float]:
        """
        Implement Reciprocal Rank Fusion algorithm.
        
        RRF formula: score(d) = sum over all rankings r: 1 / (k + rank(d, r))
        
        Args:
            vector_results: Results from vector search
            keyword_results: Results from keyword search
            k: Constant for RRF (typically 60)
        
        Returns:
            Dict mapping memory_id to RRF score
        """
        scores = defaultdict(float)
        
        # Add vector search scores
        for rank, result in enumerate(vector_results, start=1):
            memory_id = result['id']
            scores[memory_id] += 1.0 / (k + rank)
        
        # Add keyword search scores
        for rank, result in enumerate(keyword_results, start=1):
            memory_id = result['id']
            scores[memory_id] += 1.0 / (k + rank)
        
        return dict(scores)
    
    def add_memory(self, memory: MemoryItem) -> bool:
        """Add memory to both stores."""
        vector_success = self.vector_store.add_memory(memory)
        keyword_success = self.keyword_store.add_memory(memory)
        return vector_success and keyword_success
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete memory from both stores."""
        vector_success = self.vector_store.delete_memory(memory_id)
        keyword_success = self.keyword_store.delete_memory(memory_id)
        return vector_success and keyword_success
