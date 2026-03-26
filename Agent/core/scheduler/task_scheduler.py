"""
Task Scheduler - Background worker for proactive notifications (alarms, reminders).
"""
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable
from core.system_control.supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

class TaskScheduler:
    """Background scheduler for proactive agent capabilities."""
    
    def __init__(self, notification_callback: Optional[Callable] = None):
        self.db = SupabaseManager()
        self.notification_callback = notification_callback
        self.running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the background scheduler."""
        if self.running:
            logger.warning("⚠️ Scheduler already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("🚀 Task Scheduler started")
    
    async def stop(self):
        """Stop the background scheduler."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Task Scheduler stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop - checks for due tasks every minute."""
        while self.running:
            try:
                await self._check_alarms()
                await self._check_reminders()
                
                # Sleep for 60 seconds before next check
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Scheduler loop error: {e}")
                await asyncio.sleep(60)  # Continue after error
    
    async def _check_alarms(self):
        """Check for due alarms and trigger notifications."""
        if not self.db.client:
            return
        
        try:
            now = datetime.now(timezone.utc)
            
            # Get active alarms that are due
            result = await self.db._execute(
                lambda: self.db.client.table("user_alarms")
                    .select("*")
                    .eq("is_active", True)
                    .lte("alarm_time", now.isoformat())
                    .execute()
            )
            
            if result and hasattr(result, 'data') and result.data:
                for alarm in result.data:
                    await self._trigger_alarm_notification(alarm)
                    
                    # Mark alarm as inactive
                    await self.db._execute(
                        lambda: self.db.client.table("user_alarms")
                            .update({"is_active": False})
                            .eq("id", alarm['id'])
                            .execute()
                    )
                    
                    logger.info(f"⏰ Triggered alarm: {alarm['label']} for user {alarm['user_id']}")
            
        except Exception as e:
            logger.error(f"❌ Failed to check alarms: {e}")
    
    async def _check_reminders(self):
        """Check for due reminders and trigger notifications."""
        if not self.db.client:
            return
        
        try:
            now = datetime.now(timezone.utc)
            
            # Get pending reminders that are due
            result = await self.db._execute(
                lambda: self.db.client.table("user_reminders")
                    .select("*")
                    .eq("is_completed", False)
                    .lte("remind_at", now.isoformat())
                    .execute()
            )
            
            if result and hasattr(result, 'data') and result.data:
                for reminder in result.data:
                    await self._trigger_reminder_notification(reminder)
                    
                    # Mark reminder as completed
                    await self.db._execute(
                        lambda: self.db.client.table("user_reminders")
                            .update({"is_completed": True})
                            .eq("id", reminder['id'])
                            .execute()
                    )
                    
                    logger.info(f"📌 Triggered reminder: {reminder['text']} for user {reminder['user_id']}")
            
        except Exception as e:
            logger.error(f"❌ Failed to check reminders: {e}")
    
    async def _trigger_alarm_notification(self, alarm: dict):
        """Trigger notification for an alarm."""
        if self.notification_callback:
            try:
                await self.notification_callback(
                    user_id=alarm['user_id'],
                    notification_type='alarm',
                    data=alarm
                )
            except Exception as e:
                logger.error(f"❌ Failed to send alarm notification: {e}")
        else:
            logger.info(f"🔔 ALARM: {alarm['label']} for user {alarm['user_id']}")
    
    async def _trigger_reminder_notification(self, reminder: dict):
        """Trigger notification for a reminder."""
        if self.notification_callback:
            try:
                await self.notification_callback(
                    user_id=reminder['user_id'],
                    notification_type='reminder',
                    data=reminder
                )
            except Exception as e:
                logger.error(f"❌ Failed to send reminder notification: {e}")
        else:
            logger.info(f"🔔 REMINDER: {reminder['text']} for user {reminder['user_id']}")
