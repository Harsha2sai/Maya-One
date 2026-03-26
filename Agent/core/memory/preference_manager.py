"""
Preference Manager - Learn and persist user preferences.
"""
import logging
from typing import Dict, Optional, Any
from core.system_control.supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

class PreferenceManager:
    """Manages user preferences and learning."""
    
    def __init__(self):
        self.db = SupabaseManager()
    
    async def get_preferences(self, user_id: str) -> Dict[str, Any]:
        """Retrieve user preferences from Supabase."""
        if not self.db.client:
            return {}
        
        try:
            result = await self.db._execute(
                lambda: self.db.client.table("user_profiles")
                    .select("preferences")
                    .eq("id", user_id)
                    .single()
                    .execute()
            )
            
            if result and hasattr(result, 'data') and result.data:
                prefs = result.data.get('preferences', {})
                logger.info(f"📋 Retrieved preferences for user {user_id}")
                return prefs
            return {}
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to retrieve preferences: {e}")
            return {}
    
    async def update_preference(
        self, 
        user_id: str, 
        key: str, 
        value: Any
    ) -> bool:
        """Update a specific preference."""
        if not self.db.client:
            return False
        
        try:
            # Get current preferences
            current_prefs = await self.get_preferences(user_id)
            current_prefs[key] = value
            
            # Update in database
            result = await self.db._execute(
                lambda: self.db.client.table("user_profiles")
                    .update({"preferences": current_prefs})
                    .eq("id", user_id)
                    .execute()
            )
            
            if result:
                logger.info(f"✅ Updated preference '{key}' for user {user_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to update preference: {e}")
            return False
    
    async def learn_from_interaction(
        self, 
        user_id: str, 
        interaction_type: str,
        data: Dict[str, Any]
    ) -> bool:
        """
        Learn from user interactions to improve personalization.
        
        Examples:
        - interaction_type: "voice_command_preference"
        - interaction_type: "tool_usage_pattern"
        - interaction_type: "communication_style"
        """
        if not self.db.client:
            return False
        
        try:
            # Get current preferences
            prefs = await self.get_preferences(user_id)
            
            # Update learning data
            learning_key = f"learned_{interaction_type}"
            if learning_key not in prefs:
                prefs[learning_key] = []
            
            # Add new learning (keep last 10 interactions)
            prefs[learning_key].append(data)
            prefs[learning_key] = prefs[learning_key][-10:]
            
            # Save updated preferences
            result = await self.db._execute(
                lambda: self.db.client.table("user_profiles")
                    .update({"preferences": prefs})
                    .eq("id", user_id)
                    .execute()
            )
            
            if result:
                logger.info(f"🧠 Learned from {interaction_type} for user {user_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to learn from interaction: {e}")
            return False
    
    async def get_communication_style(self, user_id: str) -> str:
        """Get preferred communication style (formal, casual, technical, etc.)."""
        prefs = await self.get_preferences(user_id)
        return prefs.get("communication_style", "friendly")
    
    async def get_voice_settings(self, user_id: str) -> Dict[str, Any]:
        """Get voice-related preferences (speed, pitch, language, etc.)."""
        prefs = await self.get_preferences(user_id)
        return prefs.get("voice_settings", {
            "language": "en",
            "speed": 1.0,
            "voice_id": "default"
        })
