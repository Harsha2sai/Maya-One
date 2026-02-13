import logging
import os
import asyncio
from typing import Optional, List, Dict, Any
from livekit.agents import ChatContext
from .local_engine import LocalMemoryEngine
from .summarizer import Summarizer
from .cloud_sync import CloudSyncManager
from chaos.fault_injection import get_chaos_config

logger = logging.getLogger(__name__)

class MemoryManager:
    def __init__(self, api_key: Optional[str] = None):
        # We initialized Mem0 locally now
        self.local_engine = LocalMemoryEngine()
        self.summarizer = Summarizer(api_key=os.getenv("GROQ_API_KEY"))
        self.cloud_sync = CloudSyncManager(self.local_engine)
        asyncio.create_task(self.cloud_sync.start())
        
    async def get_user_context(self, user_id: str) -> Optional[str]:
        if not self.local_engine:
            return None

        try:
            # CHAOS: Persistence Failure Injection
            chaos_config = get_chaos_config()
            if chaos_config.enabled and chaos_config.persistence_failure_rate > 0:
                import random
                if random.random() < chaos_config.persistence_failure_rate:
                    logger.error("🔥 CHAOS: Simulating persistence failure (Storage unreadable)")
                    raise Exception("Database connection timeout (Simulated Chaos)")

            logger.info(f"🔍 Searching local memories for user: {user_id}")
            
            # Simple broad search for now to get relevant context
            results = self.local_engine.search(query="current context and preferences", user_id=user_id, limit=5)
            
            if isinstance(results, dict):
                if "results" in results:
                    results = results["results"]
                else:
                    # If it's a dict but no 'results' key, wrap it in list or treat as single item?
                    # For now assume it might be a single result or just log it
                    pass

            if not results:
                return None

            memory_items = []
            for result in results:
                if isinstance(result, dict):
                    # Extract 'memory' content from result dict
                    # Mem0 v1.1 structure usually has 'memory' key for the text
                    memory_text = result.get("memory", result.get("text", str(result)))
                else:
                    memory_text = str(result)
                memory_items.append(memory_text)
            
            if memory_items:
                # CHAOS: Memory Inflation
                # The provided snippet for inflation was incomplete, keeping original logic.
                if chaos_config.enabled and chaos_config.memory_inflation_factor > 1.0:
                     logger.warning(f"🔥 CHAOS: Inflating memory by {chaos_config.memory_inflation_factor}x")
                     original_len = len(memory_items)
                     target_len = int(original_len * chaos_config.memory_inflation_factor)
                     # Duplicate items to reach target length
                     while len(memory_items) < target_len:
                          memory_items.append(memory_items[len(memory_items) % original_len] + " (INFLATED)")

                return "Recent memories:\n" + "\n".join(f"- {m}" for m in memory_items)
                
        except Exception as e:
            logger.warning(f"⚠️ Memory search failed: {e}")
        
        return None

    async def inject_memories(self, chat_ctx: ChatContext, user_id: str):
        memory_context = await self.get_user_context(user_id)
        if memory_context:
            logger.info(f"📚 Injecting memories into chat context for {user_id}")
            chat_ctx.add_message(role="system", content=memory_context)
        else:
            logger.info(f"ℹ️ No memories found for user {user_id}")

    async def save_session_context(self, chat_ctx: ChatContext, user_id: str):
        """
        Save the current session context (messages) to local memory.
        """
        if not self.local_engine:
            logger.warning("⚠️ Local Memory engine not initialized, skipping save")
            return

        try:
            # CHAOS: Persistence Failure Injection
            chaos_config = get_chaos_config()
            if chaos_config.enabled and chaos_config.persistence_failure_rate > 0:
                import random
                if random.random() < chaos_config.persistence_failure_rate:
                    logger.error("🔥 CHAOS: Simulating persistence failure (Storage unwritable)")
                    raise Exception("Database write error (Simulated Chaos)")

            logger.info(f"💾 Saving session context for user: {user_id}")
            
            # Extract messages from ChatContext
            messages_to_save = []
            # messages is a method in newer livekit-agents versions or just this env
            messages_list = chat_ctx.messages() if callable(chat_ctx.messages) else chat_ctx.messages
            
            for msg in messages_list:
                # Ensure we have content
                content = msg.content
                if not content:
                    continue

                # Handle LiveKit multimodal content (lists)
                if isinstance(content, list):
                    content_str = " ".join([str(c) for c in content if isinstance(c, str)])
                    # If it was a list of complex objects, str() might not be enough but for text it is.
                    if not content_str:
                        content_str = str(content)
                else:
                    content_str = str(content)

                messages_to_save.append({
                    "role": msg.role,
                    "content": content_str
                })
            
            if messages_to_save:
                # Add to local engine
                if self.local_engine.add(messages=messages_to_save, user_id=user_id):
                    logger.info(f"✅ Successfully saved {len(messages_to_save)} messages to local memory")
                else:
                    logger.warning("⚠️ Failed to add messages to local memory (check engine logs)")
            else:
                logger.info("ℹ️ No messages to save")
                
        except Exception as e:
            logger.error(f"❌ Failed to save session context: {e}")

    async def summarize_session(self, chat_ctx: ChatContext, threshold: int = 20):
        """
        Summarize the session if message count exceeds threshold.
        """
        if not self.summarizer:
            return

        messages = chat_ctx.messages() if callable(chat_ctx.messages) else chat_ctx.messages
        if len(messages) < threshold:
            return

        logger.info(f"🧹 Session length ({len(messages)}) exceeds threshold ({threshold}). Summarizing...")
        
        # Convert LiveKit messages to dicts for summarizer
        msg_dicts = []
        for msg in messages:
            content = msg.content
            if isinstance(content, list):
                content = " ".join([str(c) for c in content if isinstance(c, str)])
            else:
                content = str(content)
            
            msg_dicts.append({"role": msg.role, "content": content})

        summary = await self.summarizer.summarize_messages(msg_dicts)
        
        if summary:
            logger.info(f"📝 Summary generated: {summary[:50]}...")
            
            # Here we would typically clear the context and inject the summary.
            # For this phase, we'll just log it and perhaps save it as a "memory"
            # In a full implementation, we'd replace the chat_ctx messages.
            
            # Save summary to local memory as a consolidated memory
            self.local_engine.add(
                messages=[{"role": "system", "content": f"Previous conversation summary: {summary}"}],
                user_id="system_summary"
            )
            return summary
        return None
