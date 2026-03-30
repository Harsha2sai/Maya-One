
import logging
import sys
from typing import List, Dict, Any, Optional, TYPE_CHECKING

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
        logger.info("HybridMemoryManager initialized")
    
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
