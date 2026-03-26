"""
Supabase Client for User Authentication and Management
Handles persistent user identity for Mem0AI memory consistency
"""

import os
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

class SupabaseManager:
    """Manages Supabase authentication and user data"""
    
    def __init__(self):
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY")  # Use service key for backend
        
        if not supabase_url or not supabase_key:
            logger.warning("Supabase credentials not found - user authentication disabled")
            self.client = None
        else:
            self.client: Client = create_client(supabase_url, supabase_key)
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user profile by Supabase user ID
        
        Args:
            user_id: Supabase auth user UUID
            
        Returns:
            User profile dict or None
        """
        if not self.client:
            return None
            
        try:
            response = self.client.table('user_profiles')\
                .select('*')\
                .eq('id', user_id)\
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to get user {user_id}: {e}")
            return None
    
    def create_session_record(
        self,
        user_id: str,
        room_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Create a session record when user starts a LiveKit session
        
        Args:
            user_id: Supabase user ID
            room_id: LiveKit room/session ID
            metadata: Additional session metadata
            
        Returns:
            Session ID or None
        """
        if not self.client:
            return None
            
        try:
            response = self.client.table('user_sessions').insert({
                'user_id': user_id,
                'livekit_room_id': room_id,
                'metadata': metadata or {}
            }).execute()
            
            session_id = response.data[0]['id'] if response.data else None
            logger.info(f"Created session {session_id} for user {user_id}")
            return session_id
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return None
    
    def end_session(self, room_id: str):
        """
        Mark session as ended
        
        Args:
            room_id: LiveKit room ID
        """
        if not self.client:
            return
            
        try:
            self.client.table('user_sessions')\
                .update({'ended_at': 'now()'})\
                .eq('livekit_room_id', room_id)\
                .execute()
            logger.info(f"Ended session for room {room_id}")
        except Exception as e:
            logger.error(f"Failed to end session: {e}")
    
    def get_user_sessions(self, user_id: str, limit: int = 10) -> list:
        """
        Get recent sessions for a user
        
        Args:
            user_id: Supabase user ID
            limit: Max number of sessions to return
            
        Returns:
            List of session records
        """
        if not self.client:
            return []
            
        try:
            response = self.client.table('user_sessions')\
                .select('*')\
                .eq('user_id', user_id)\
                .order('started_at', desc=True)\
                .limit(limit)\
                .execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get user sessions: {e}")
            return []
    async def create_note(self, user_id: str, title: str, content: str) -> Optional[Dict]:
        """Async create note"""
        if not self.client: return None
        
        def _insert():
            return self.client.table('user_notes').insert({
                'user_id': user_id,
                'title': title,
                'content': content
            }).execute()
            
        try:
            response = await asyncio.to_thread(_insert)
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to create note: {e}")
            return None

    async def get_notes(self, user_id: str) -> List[Dict]:
        """Async get user notes"""
        if not self.client: return []
        
        def _fetch():
            return self.client.table('user_notes')\
                .select('*')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .execute()
                
        try:
            response = await asyncio.to_thread(_fetch)
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to fetch notes: {e}")
            return []

    async def delete_note(self, note_id: int, user_id: str) -> bool:
        """Async delete note"""
        if not self.client: return False
        
        def _delete():
            return self.client.table('user_notes')\
                .delete()\
                .eq('id', note_id)\
                .eq('user_id', user_id)\
                .execute()
                
        try:
            await asyncio.to_thread(_delete)
            return True
        except Exception as e:
            logger.error(f"Failed to delete note: {e}")
            return False

    async def create_alarm(self, user_id: str, alarm_time: datetime, label: str = "Alarm") -> Optional[Dict]:
        """Async create alarm"""
        if not self.client: return None
        
        def _insert():
            return self.client.table('user_alarms').insert({
                'user_id': user_id,
                'alarm_time': alarm_time.isoformat(),
                'label': label,
                'is_active': True
            }).execute()
            
        try:
            response = await asyncio.to_thread(_insert)
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to create alarm: {e}")
            return None

    async def get_alarms(self, user_id: str) -> List[Dict]:
        """Async get active alarms"""
        if not self.client: return []
        
        def _fetch():
            return self.client.table('user_alarms')\
                .select('*')\
                .eq('user_id', user_id)\
                .eq('is_active', True)\
                .order('alarm_time', desc=False)\
                .execute()
                
        try:
            response = await asyncio.to_thread(_fetch)
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to fetch alarms: {e}")
            return []
            

    async def delete_alarm(self, alarm_id: int, user_id: str) -> bool:
        """Async delete alarm"""
        if not self.client: return False
        
        def _delete():
            return self.client.table('user_alarms')\
                .delete()\
                .eq('id', alarm_id)\
                .eq('user_id', user_id)\
                .execute()
                
        try:
            await asyncio.to_thread(_delete)
            return True
        except Exception as e:
            logger.error(f"Failed to delete alarm: {e}")
            return False

    # ============================================
    # Reminder Methods
    # ============================================

    async def create_reminder(self, user_id: str, text: str, remind_at: datetime) -> Optional[Dict]:
        """Async create reminder"""
        if not self.client: return None
        
        def _insert():
            return self.client.table('user_reminders').insert({
                'user_id': user_id,
                'text': text,
                'remind_at': remind_at.isoformat(),
                'is_completed': False
            }).execute()
            
        try:
            response = await asyncio.to_thread(_insert)
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to create reminder: {e}")
            return None

    async def get_reminders(self, user_id: str) -> List[Dict]:
        """Async get active reminders"""
        if not self.client: return []
        
        def _fetch():
            return self.client.table('user_reminders')\
                .select('*')\
                .eq('user_id', user_id)\
                .eq('is_completed', False)\
                .order('remind_at', desc=False)\
                .execute()
                
        try:
            response = await asyncio.to_thread(_fetch)
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to fetch reminders: {e}")
            return []
            
    async def delete_reminder(self, reminder_id: int, user_id: str) -> bool:
        """Async delete reminder"""
        if not self.client: return False
        
        def _delete():
            return self.client.table('user_reminders')\
                .delete()\
                .eq('id', reminder_id)\
                .eq('user_id', user_id)\
                .execute()
                
        try:
            await asyncio.to_thread(_delete)
            return True
        except Exception as e:
            logger.error(f"Failed to delete reminder: {e}")
            return False

    # ============================================
    # Calendar Event Methods
    # ============================================

    async def create_calendar_event(
        self, 
        user_id: str, 
        title: str, 
        start_time: datetime, 
        end_time: datetime,
        description: Optional[str] = None
    ) -> Optional[Dict]:
        """Async create calendar event"""
        if not self.client: return None
        
        def _insert():
            return self.client.table('user_calendar_events').insert({
                'user_id': user_id,
                'title': title,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'description': description
            }).execute()
            
        try:
            response = await asyncio.to_thread(_insert)
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to create calendar event: {e}")
            return None

    async def get_calendar_events(self, user_id: str) -> List[Dict]:
        """Async get upcoming calendar events"""
        if not self.client: return []
        
        def _fetch():
            # Get events from now onwards
            now = datetime.now().isoformat()
            return self.client.table('user_calendar_events')\
                .select('*')\
                .eq('user_id', user_id)\
                .gte('start_time', now)\
                .order('start_time', desc=False)\
                .execute()
                
        try:
            response = await asyncio.to_thread(_fetch)
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to fetch calendar events: {e}")
            return []
            
    async def delete_calendar_event(self, event_id: int, user_id: str) -> bool:
        """Async delete calendar event"""
        if not self.client: return False
        
        def _delete():
            return self.client.table('user_calendar_events')\
                .delete()\
                .eq('id', event_id)\
                .eq('user_id', user_id)\
                .execute()
                
        try:
            await asyncio.to_thread(_delete)
            return True
        except Exception as e:
            logger.error(f"Failed to delete calendar event: {e}")
            return False

# Global instance
supabase_manager = SupabaseManager()

