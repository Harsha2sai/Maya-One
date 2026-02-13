"""
Context Analyzer - Analyze user patterns for proactive suggestions.
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from core.system_control.supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

class ContextAnalyzer:
    """Analyzes user behavior patterns for proactive suggestions."""
    
    def __init__(self):
        self.db = SupabaseManager()
    
    async def analyze_usage_patterns(self, user_id: str) -> Dict[str, any]:
        """Analyze user's interaction patterns."""
        if not self.db.client:
            return {}
        
        try:
            # Get user's session history
            result = await self.db._execute(
                lambda: self.db.client.table("user_sessions")
                    .select("*")
                    .eq("user_id", user_id)
                    .order("started_at", desc=True)
                    .limit(30)
                    .execute()
            )
            
            if not result or not hasattr(result, 'data') or not result.data:
                return {}
            
            sessions = result.data
            
            # Analyze patterns
            patterns = {
                "total_sessions": len(sessions),
                "most_active_time": await self._find_most_active_time(sessions),
                "average_session_duration": await self._calculate_avg_duration(sessions),
                "frequent_tools": await self._get_frequent_tools(user_id)
            }
            
            logger.info(f"📊 Analyzed patterns for user {user_id}")
            return patterns
            
        except Exception as e:
            logger.error(f"❌ Failed to analyze patterns: {e}")
            return {}
    
    async def _find_most_active_time(self, sessions: List[Dict]) -> Optional[str]:
        """Find the hour of day when user is most active."""
        try:
            hour_counts = {}
            for session in sessions:
                started_at = datetime.fromisoformat(session['started_at'].replace('Z', '+00:00'))
                hour = started_at.hour
                hour_counts[hour] = hour_counts.get(hour, 0) + 1
            
            if hour_counts:
                most_active_hour = max(hour_counts, key=hour_counts.get)
                return f"{most_active_hour:02d}:00"
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to find most active time: {e}")
            return None
    
    async def _calculate_avg_duration(self, sessions: List[Dict]) -> Optional[float]:
        """Calculate average session duration in minutes."""
        try:
            durations = []
            for session in sessions:
                if session.get('ended_at'):
                    started = datetime.fromisoformat(session['started_at'].replace('Z', '+00:00'))
                    ended = datetime.fromisoformat(session['ended_at'].replace('Z', '+00:00'))
                    duration = (ended - started).total_seconds() / 60
                    durations.append(duration)
            
            if durations:
                return sum(durations) / len(durations)
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to calculate avg duration: {e}")
            return None
    
    async def _get_frequent_tools(self, user_id: str) -> List[str]:
        """Get most frequently used tools."""
        # This would require tool usage tracking in conversation_history
        # For now, return empty list as placeholder
        return []
    
    async def suggest_next_action(self, user_id: str) -> Optional[str]:
        """Generate proactive suggestion based on context."""
        try:
            patterns = await self.analyze_usage_patterns(user_id)
            
            if not patterns:
                return None
            
            # Get upcoming alarms/reminders
            upcoming_alarms = await self._get_upcoming_alarms(user_id)
            upcoming_reminders = await self._get_upcoming_reminders(user_id)
            
            suggestions = []
            
            if upcoming_alarms:
                suggestions.append(f"You have {len(upcoming_alarms)} upcoming alarm(s)")
            
            if upcoming_reminders:
                suggestions.append(f"You have {len(upcoming_reminders)} pending reminder(s)")
            
            if patterns.get("most_active_time"):
                suggestions.append(f"You're usually most active around {patterns['most_active_time']}")
            
            if suggestions:
                return " | ".join(suggestions)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to generate suggestion: {e}")
            return None
    
    async def _get_upcoming_alarms(self, user_id: str) -> List[Dict]:
        """Get upcoming alarms for the next 24 hours."""
        if not self.db.client:
            return []
        
        try:
            now = datetime.utcnow()
            tomorrow = now + timedelta(days=1)
            
            result = await self.db._execute(
                lambda: self.db.client.table("user_alarms")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("is_active", True)
                    .gte("alarm_time", now.isoformat())
                    .lte("alarm_time", tomorrow.isoformat())
                    .execute()
            )
            
            if result and hasattr(result, 'data'):
                return result.data
            return []
            
        except Exception as e:
            logger.error(f"❌ Failed to get upcoming alarms: {e}")
            return []
    
    async def _get_upcoming_reminders(self, user_id: str) -> List[Dict]:
        """Get upcoming reminders for the next 24 hours."""
        if not self.db.client:
            return []
        
        try:
            now = datetime.utcnow()
            tomorrow = now + timedelta(days=1)
            
            result = await self.db._execute(
                lambda: self.db.client.table("user_reminders")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("is_completed", False)
                    .gte("remind_at", now.isoformat())
                    .lte("remind_at", tomorrow.isoformat())
                    .execute()
            )
            
            if result and hasattr(result, 'data'):
                return result.data
            return []
            
        except Exception as e:
            logger.error(f"❌ Failed to get upcoming reminders: {e}")
            return []
