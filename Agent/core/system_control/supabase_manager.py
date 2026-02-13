import os
import asyncio
import logging
from typing import List, Dict, Optional, Any
from supabase import create_client, Client
import time
from functools import wraps

logger = logging.getLogger(__name__)

def retry_with_backoff(max_retries=3, base_delay=1.0):
    """Decorator for retry logic with exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"⚠️ Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
            return None
        return wrapper
    return decorator

class SupabaseManager:
    """
    Manages asynchronous interactions with Supabase using asyncio.to_thread
    to avoid blocking the main event loop.
    """
    def __init__(self):
        self.client: Optional[Client] = None
        self._init_client()

    def _init_client(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not url or not key:
            logger.warning("⚠️ Supabase credentials (SUPABASE_URL, SUPABASE_SERVICE_KEY) not found. Persistence disabled.")
            return

        try:
            self.client = create_client(url, key)
            logger.info("✅ Supabase Client Initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase client: {e}")

    @retry_with_backoff(max_retries=3, base_delay=0.5)
    async def _execute(self, query_func) -> Any:
        """Helper to run synchronous Supabase calls in a thread with retry."""
        if not self.client:
            logger.warning("⚠️ Supabase client not initialized")
            return None
        try:
            return await asyncio.to_thread(query_func)
        except Exception as e:
            logger.error(f"❌ Supabase Query Error: {e}")
            raise  # Re-raise for retry decorator

    # --- Alarms ---
    async def create_alarm(self, user_id: str, alarm_time: str, label: str = "Alarm") -> bool:
        def _query():
            return self.client.table("user_alarms").insert({
                "user_id": user_id,
                "alarm_time": alarm_time,
                "label": label,
                "is_active": True
            }).execute()
        
        result = await self._execute(_query)
        return bool(result and result.data)

    async def get_active_alarms(self, user_id: str) -> List[Dict]:
        def _query():
            return self.client.table("user_alarms").select("*")\
                .eq("user_id", user_id)\
                .eq("is_active", True)\
                .order("alarm_time")\
                .execute()
        
        result = await self._execute(_query)
        return result.data if result else []

    async def delete_alarm(self, user_id: str, alarm_id: int) -> bool:
        def _query():
            return self.client.table("user_alarms").delete()\
                .eq("user_id", user_id)\
                .eq("id", alarm_id)\
                .execute()
        
        result = await self._execute(_query)
        return bool(result and result.data)

    # --- Reminders ---
    async def create_reminder(self, user_id: str, text: str, remind_at: str) -> bool:
        def _query():
            return self.client.table("user_reminders").insert({
                "user_id": user_id,
                "text": text,
                "remind_at": remind_at,
                "is_completed": False
            }).execute()
        
        result = await self._execute(_query)
        return bool(result and result.data)

    async def get_pending_reminders(self, user_id: str) -> List[Dict]:
        def _query():
            return self.client.table("user_reminders").select("*")\
                .eq("user_id", user_id)\
                .eq("is_completed", False)\
                .order("remind_at")\
                .execute()
        
        result = await self._execute(_query)
        return result.data if result else []

    # --- Notes ---
    async def create_note(self, user_id: str, title: str, content: str) -> bool:
        def _query():
            return self.client.table("user_notes").insert({
                "user_id": user_id,
                "title": title,
                "content": content
            }).execute()
        
        result = await self._execute(_query)
        return bool(result and result.data)

    async def get_notes(self, user_id: str, limit: int = 10) -> List[Dict]:
        def _query():
            return self.client.table("user_notes").select("*")\
                .eq("user_id", user_id)\
                .order("updated_at", desc=True)\
                .limit(limit)\
                .execute()
        
        result = await self._execute(_query)
        return result.data if result else []

    # --- Sessions ---
    async def create_session_record(self, user_id: str, room_id: str, metadata: Dict = {}) -> bool:
        def _query():
            return self.client.table("user_sessions").insert({
                "user_id": user_id,
                "livekit_room_id": room_id,
                "metadata": metadata
            }).execute()
        
        result = await self._execute(_query)
        return bool(result and result.data)
