import logging
import os
from typing import List, Optional
from mem0 import AsyncMemoryClient
from livekit.agents import ChatContext

logger = logging.getLogger(__name__)

class MemoryManager:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("MEM0_API_KEY")
        self.client = None
        if self.api_key:
            try:
                self.client = AsyncMemoryClient(api_key=self.api_key)
                logger.info("✅ Mem0 initialized successfully")
            except Exception as e:
                logger.error(f"❌ Mem0 init failed: {e}")

    async def get_user_context(self, user_id: str) -> Optional[str]:
        if not self.client:
            return None

        try:
            logger.info(f"🔍 Searching memories for user: {user_id}")
            
            search_queries = [
                "user information and preferences",
                "user profile",
                "previous conversation",
                user_id
            ]
            
            memories_found = []
            for query in search_queries:
                try:
                    results = await self.client.search(
                        query=query,
                        filters={"user_id": user_id},
                        limit=3
                    )
                    
                    if results:
                        memories_list = results.get('results', []) if isinstance(results, dict) else []
                        if memories_list:
                            memories_found.extend(memories_list)
                            logger.info(f"✅ Found {len(memories_list)} memories for query: '{query}'")
                            break
                            
                except Exception as e:
                    logger.debug(f"⚠️ Search query '{query}' failed: {e}")
                    continue
            
            if not memories_found:
                return None

            memory_items = []
            for result in memories_found:
                if isinstance(result, dict):
                    memory_text = result.get("memory", str(result))
                else:
                    memory_text = str(result)
                memory_items.append(memory_text)
            
            if memory_items:
                return "Previous context from memory:\n" + "\n".join(f"- {m}" for m in memory_items)
                
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
