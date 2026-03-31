
import logging
import sys
import os
import re
import time
import hashlib
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from collections import deque

if TYPE_CHECKING:
    from livekit.agents import ChatContext

from core.memory.hybrid_retriever import HybridRetriever
from core.memory.memory_models import MemoryItem, MemorySource
from datetime import datetime
from core.telemetry.runtime_metrics import RuntimeMetrics

logger = logging.getLogger(__name__)

class HybridMemoryManager:
    """
    OpenClaw-style hybrid memory manager.
    Handles storage and retrieval of memories across conversations, tasks, and tools.
    """
    
    def __init__(self):
        self.retriever = HybridRetriever()
        self._duplicate_window_s = max(10, int(os.getenv("MEMORY_DUPLICATE_WINDOW_S", "180")))
        self._recent_write_keys: dict[str, float] = {}
        self._recent_write_order: deque[str] = deque(maxlen=4096)
        logger.info("HybridMemoryManager initialized")

    def _remember_write_key(self, key: str) -> bool:
        """
        Return True when key is seen recently (duplicate window); otherwise register and return False.
        """
        now = time.time()
        expiry = now - self._duplicate_window_s

        while self._recent_write_order:
            oldest = self._recent_write_order[0]
            ts = self._recent_write_keys.get(oldest, 0.0)
            if ts >= expiry:
                break
            self._recent_write_order.popleft()
            self._recent_write_keys.pop(oldest, None)

        if key in self._recent_write_keys and self._recent_write_keys[key] >= expiry:
            return True

        self._recent_write_keys[key] = now
        self._recent_write_order.append(key)
        return False

    @staticmethod
    def _extract_profile_name(user_msg: str) -> Optional[str]:
        text = (user_msg or "").strip()
        if not text:
            return None
        match = re.match(
            r"^\s*(?:my\s+name\s+is|i\s+am|i'm|call\s+me)\s+([A-Za-z][A-Za-z0-9' -]{0,40})\s*$",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None
        return match.group(1).strip(" .,!?:;\"'")

    def store_profile_fact(
        self,
        *,
        user_id: Optional[str],
        session_id: Optional[str],
        field: str,
        value: str,
    ) -> bool:
        """
        Store canonical user profile facts (e.g., name) for safer recall.
        """
        safe_field = str(field or "").strip().lower()
        safe_value = str(value or "").strip()
        if not safe_field or not safe_value:
            return False

        dedupe_basis = f"profile|{user_id or ''}|{session_id or ''}|{safe_field}|{safe_value.lower()}"
        dedupe_key = hashlib.sha1(dedupe_basis.encode("utf-8")).hexdigest()
        if self._remember_write_key(dedupe_key):
            logger.info("Skipped duplicate profile fact write field=%s user_id=%s session_id=%s", safe_field, user_id, session_id)
            return True

        metadata: Dict[str, Any] = {
            "type": "profile_fact",
            "memory_kind": "profile_fact",
            "field": safe_field,
            "value": safe_value,
        }
        if user_id:
            metadata["user_id"] = user_id
        if session_id:
            metadata["session_id"] = session_id

        try:
            memory = MemoryItem(
                text=f"User profile fact: {safe_field}={safe_value}",
                source=MemorySource.CONVERSATION,
                metadata=metadata,
            )
            success = self.retriever.add_memory(memory)
            if success:
                RuntimeMetrics.increment("memory_stores_total")
            return success
        except Exception as e:
            logger.error(f"Failed to store profile fact: {e}")
            return False
    
    def store_conversation_turn(
        self,
        user_msg: str,
        assistant_msg: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """
        Store a conversation turn as memory.
        """
        try:
            dedupe_basis = f"turn|{user_id or ''}|{session_id or ''}|{re.sub(r'\\s+', ' ', (user_msg or '').strip().lower())}"
            dedupe_key = hashlib.sha1(dedupe_basis.encode("utf-8")).hexdigest()
            if self._remember_write_key(dedupe_key):
                logger.info("Skipped duplicate conversation memory write user_id=%s session_id=%s", user_id, session_id)
                return True

            profile_name = self._extract_profile_name(user_msg)
            if profile_name:
                self.store_profile_fact(
                    user_id=user_id,
                    session_id=session_id,
                    field="name",
                    value=profile_name,
                )

            text = f"User: {user_msg}\nAssistant: {assistant_msg}"
            combined_metadata = metadata or {}
            if user_id:
                combined_metadata = {**combined_metadata, "user_id": user_id}
            if session_id:
                combined_metadata = {**combined_metadata, "session_id": session_id}
            memory = MemoryItem(
                text=text,
                source=MemorySource.CONVERSATION,
                metadata=combined_metadata,
            )
            success = self.retriever.add_memory(memory)
            if success:
                logger.info(f"Stored conversation memory: {memory.id}")
                RuntimeMetrics.increment("memory_stores_total")
            return success
        except Exception as e:
            logger.error(f"Failed to store conversation turn: {e}")
            return False
    
    def store_task_result(
        self,
        task_id: str,
        result: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Store a task result as memory.
        """
        try:
            memory = MemoryItem(
                text=result,
                source=MemorySource.TASK_RESULT,
                metadata={
                    "task_id": task_id,
                    **(metadata or {})
                }
            )
            
            success = self.retriever.add_memory(memory)
            if success:
                logger.info(f"Stored task result memory: {memory.id}")
                RuntimeMetrics.increment("memory_stores_total")
            return success
            
        except Exception as e:
            logger.error(f"Failed to store task result: {e}")
            return False
    
    def store_tool_output(
        self,
        tool_name: str,
        output: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Store a tool output as memory.
        """
        try:
            memory = MemoryItem(
                text=output,
                source=MemorySource.TOOL_OUTPUT,
                metadata={
                    "tool_name": tool_name,
                    **(metadata or {})
                }
            )
            
            success = self.retriever.add_memory(memory)
            if success:
                logger.debug(f"Stored tool output memory: {memory.id}")
                RuntimeMetrics.increment("memory_stores_total")
            return success
            
        except Exception as e:
            logger.error(f"Failed to store tool output: {e}")
            return False
    
    async def get_user_context(self, user_id: str, k: int = 5) -> Optional[str]:
        """
        Retrieve relevant memories for a user and format them as context.
        Returns a formatted string of memories or None if no memories found.
        
        This method is called by context_builder.py to inject long-term memories
        into the LLM context.
        """
        try:
            # Use the existing retrieve_relevant_memories method
            # Query with user_id to get user-specific memories
            memories = self.retrieve_relevant_memories(
                query="user information name preferences background context",
                k=k,
                user_id=user_id,
                origin="chat",
            )
            
            if not memories:
                logger.debug(f"No memories found for user: {user_id}")
                return None
                
            # Format memories as a string
            formatted = []
            for mem in memories:
                text = mem.get('text', '')
                source = mem.get('source', 'unknown')
                formatted.append(f"[{source}] {text}")
                
            result = "\n".join(formatted)
            logger.debug(f"Retrieved {len(memories)} memories for user {user_id}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get user context: {e}")
            return None
    
    def store_file_content(
        self,
        file_path: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Store file content as memory.
        """
        try:
            memory = MemoryItem(
                text=content,
                source=MemorySource.FILE,
                metadata={
                    "file_path": file_path,
                    **(metadata or {})
                }
            )
            
            success = self.retriever.add_memory(memory)
            if success:
                logger.info(f"Stored file memory: {memory.id}")
                RuntimeMetrics.increment("memory_stores_total")
            return success
            
        except Exception as e:
            logger.error(f"Failed to store file content: {e}")
            return False
    
    def retrieve_relevant_memories(
        self,
        query: str,
        k: int = 5,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        origin: str = "chat",
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant memories for a given query.
        Uses hybrid retrieval (vector + keyword).
        """
        try:
            RuntimeMetrics.increment("memory_queries_total")
            memories = self.retriever.retrieve(
                query,
                k=k,
                user_id=user_id,
                session_id=session_id,
                origin=origin,
            )
            logger.info(f"Retrieved {len(memories)} relevant memories for query")
            return memories
            
        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")
            return []

    async def retrieve_relevant_memories_async(
        self,
        query: str,
        k: int = 5,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        origin: str = "chat",
    ) -> List[Dict[str, Any]]:
        """Async retrieval wrapper with timeout/error handling from HybridRetriever."""
        try:
            RuntimeMetrics.increment("memory_queries_total")
            memories = await self.retriever.retrieve_async(
                query,
                k=k,
                user_id=user_id,
                session_id=session_id,
                origin=origin,
            )
            logger.info(f"Retrieved {len(memories)} relevant memories for query")
            return memories
        except Exception as e:
            logger.error(f"Failed to retrieve memories async: {e}")
            return []

    async def retrieve_relevant_memories_with_scope_fallback_async(
        self,
        query: str,
        k: int = 5,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        origin: str = "chat",
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories with session->user scope widening fallback.
        """
        try:
            RuntimeMetrics.increment("memory_queries_total")
            memories = await self.retriever.retrieve_with_scope_fallback(
                query=query,
                user_id=user_id,
                session_id=session_id,
                origin=origin,
                k=k,
            )
            logger.info(f"Retrieved {len(memories)} relevant memories for query")
            return memories
        except Exception as e:
            logger.error(f"Failed to retrieve memories with scope fallback async: {e}")
            return []
    
    async def inject_memories(self, chat_ctx: "ChatContext", user_id: str):
        """
        Inject relevant broad context based on user profile/preferences.
        """
        try:
            # Query for general user context or recent important facts
            # In Phase 6, we use retrieve_relevant_memories for this
            memories = self.retrieve_relevant_memories(
                f"context and preferences for {user_id}",
                k=3,
                user_id=user_id,
                origin="chat",
            )
            if memories:
                formatted_mem = "\n".join([f"- {m['text']}" for m in memories])
                chat_ctx.add_message(
                    role="system", 
                    content=f"Past context for {user_id}:\n{formatted_mem}"
                )
                logger.info(f"📚 Injected {len(memories)} memories into context")
            else:
                logger.info(f"ℹ️ No initial memories to inject for {user_id}")
        except Exception as e:
            logger.error(f"Failed to inject memories: {e}")

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        return self.retriever.delete_memory(memory_id)
    
    def get_stats(self) -> Dict[str, int]:
        """Get memory store statistics."""
        return {
            "vector_count": self.retriever.vector_store.count(),
            "keyword_count": self.retriever.keyword_store.count()
        }
