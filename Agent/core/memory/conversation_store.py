"""
Conversation Store - Persist chat history to Supabase for cross-session continuity.
"""
import logging
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from core.system_control.supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

class ConversationStore:
    """Manages persistent conversation history in Supabase."""
    
    def __init__(self):
        self.db = SupabaseManager()
    
    async def save_message(
        self, 
        user_id: str, 
        session_id: str,
        role: str, 
        content: str,
        metadata: Optional[Dict] = None
    ) -> bool:
        """Save a single message to conversation history."""
        if not self.db.client:
            logger.warning("⚠️ Supabase not initialized, skipping message save")
            return False
        
        try:
            data = {
                "user_id": user_id,
                "session_id": session_id,
                "role": role,
                "content": content,
                "metadata": metadata or {},
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = await self.db._execute(
                lambda: self.db.client.table("conversation_history").insert(data).execute()
            )
            
            if result:
                logger.debug(f"💾 Saved {role} message for session {session_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to save message: {e}")
            return False
    
    async def get_session_history(
        self, 
        session_id: str, 
        limit: int = 50
    ) -> List[Dict]:
        """Retrieve conversation history for a session."""
        if not self.db.client:
            return []
        
        try:
            result = await self.db._execute(
                lambda: self.db.client.table("conversation_history")
                    .select("*")
                    .eq("session_id", session_id)
                    .order("created_at", desc=False)
                    .limit(limit)
                    .execute()
            )
            
            if result and hasattr(result, 'data'):
                logger.info(f"📚 Retrieved {len(result.data)} messages for session {session_id}")
                return result.data
            return []
            
        except Exception as e:
            logger.error(f"❌ Failed to retrieve session history: {e}")
            return []
    
    async def get_user_recent_context(
        self, 
        user_id: str, 
        limit: int = 10
    ) -> List[Dict]:
        """Get recent conversation context across all user sessions."""
        if not self.db.client:
            return []
        
        try:
            result = await self.db._execute(
                lambda: self.db.client.table("conversation_history")
                    .select("*")
                    .eq("user_id", user_id)
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
            )
            
            if result and hasattr(result, 'data'):
                # Reverse to get chronological order
                messages = list(reversed(result.data))
                logger.info(f"📖 Retrieved {len(messages)} recent messages for user {user_id}")
                return messages
            return []
            
        except Exception as e:
            logger.error(f"❌ Failed to retrieve user context: {e}")
            return []
    
    async def clear_old_sessions(self, days: int = 30) -> bool:
        """Archive or delete conversations older than specified days."""
        if not self.db.client:
            return False
        
        try:
            cutoff_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_date = cutoff_date.replace(day=cutoff_date.day - days)
            
            result = await self.db._execute(
                lambda: self.db.client.table("conversation_history")
                    .delete()
                    .lt("created_at", cutoff_date.isoformat())
                    .execute()
            )
            
            if result:
                logger.info(f"🗑️ Cleared conversations older than {days} days")
                return True
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to clear old sessions: {e}")
            return False
