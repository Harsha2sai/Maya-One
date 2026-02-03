import os
import asyncio
import logging
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class SupabaseManager:
    """Manages Supabase authentication and user data for Zoya Agent"""
    
    def __init__(self):
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not supabase_url or not supabase_key:
            logger.warning("⚠️ Supabase credentials not found - user authentication and persistence disabled")
            self.client = None
        else:
            try:
                self.client: Client = create_client(supabase_url, supabase_key)
                logger.info("✅ Supabase Manager Initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Supabase client: {e}")
                self.client = None

    async def _safe_db_call(self, operation):
        """Wrapper to run synchronous Supabase calls in a separate thread to avoid blocking"""
        if not self.client:
            return None
        try:
            return await asyncio.to_thread(operation)
        except Exception as e:
            logger.error(f"❌ Supabase DB Error: {e}")
            return None

    # --- Session Management ---
    
    async def create_session_record(self, user_id: str, room_id: str, metadata: Optional[Dict[str, Any]] = None):
        def _op():
            return self.client.table('user_sessions').insert({
                'user_id': user_id,
                'livekit_room_id': room_id,
                'metadata': metadata or {}
            }).execute()
        
        result = await self._safe_db_call(_op)
        if result and result.data:
            logger.info(f"Created session for user {user_id}")
            return result.data[0]['id']
        return None

    async def end_session(self, room_id: str):
        def _op():
            return self.client.table('user_sessions')\
                .update({'ended_at': 'now()'})\
                .eq('livekit_room_id', room_id)\
                .execute()
        await self._safe_db_call(_op)

    # --- Alarms ---
    
    async def create_alarm(self, user_id: str, alarm_time: str, label: str):
        def _op():
            return self.client.table("user_alarms").insert({
                "user_id": user_id,
                "alarm_time": alarm_time,
                "label": label
            }).execute()
        
        result = await self._safe_db_call(_op)
        return result.data[0] if result and result.data else None

    async def get_alarms(self, user_id: str):
        def _op():
            return self.client.table("user_alarms")\
                .select("*")\
                .eq("user_id", user_id)\
                .execute()
        
        result = await self._safe_db_call(_op)
        return result.data if result else []

    async def delete_alarm(self, user_id: str, alarm_id: int):
        def _op():
            return self.client.table("user_alarms")\
                .delete()\
                .eq("user_id", user_id)\
                .eq("id", alarm_id)\
                .execute()
        await self._safe_db_call(_op)

    # --- Reminders ---
    
    async def create_reminder(self, user_id: str, text: str, remind_at: str):
        def _op():
            return self.client.table("user_reminders").insert({
                "user_id": user_id,
                "text": text,
                "remind_at": remind_at
            }).execute()
        
        result = await self._safe_db_call(_op)
        return result.data[0] if result and result.data else None

    async def get_reminders(self, user_id: str):
        def _op():
            return self.client.table("user_reminders")\
                .select("*")\
                .eq("user_id", user_id)\
                .execute()
        
        result = await self._safe_db_call(_op)
        return result.data if result else []

    # --- Notes ---
    
    async def create_note(self, user_id: str, title: str, content: str):
        def _op():
            return self.client.table("user_notes").insert({
                "user_id": user_id,
                "title": title,
                "content": content
            }).execute()
        
        result = await self._safe_db_call(_op)
        return result.data[0] if result and result.data else None

    async def get_notes(self, user_id: str):
        def _op():
            return self.client.table("user_notes")\
                .select("*")\
                .eq("user_id", user_id)\
                .execute()
        
        result = await self._safe_db_call(_op)
        return result.data if result else []

# Singleton instance
supabase_manager = SupabaseManager()
