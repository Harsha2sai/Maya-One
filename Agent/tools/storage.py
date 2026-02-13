import logging
from typing import Annotated, Optional
from livekit.agents import function_tool, RunContext
from .base import get_user_id
from core.system_control.supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

# Initialize Manager
db = SupabaseManager()

# --- Alarms ---
@function_tool()
async def set_alarm(
    context: RunContext,
    time: str,
    label: str = "Alarm"
) -> str:
    """Set an alarm for a specific time."""
    user_id = get_user_id(context)
    logger.info(f"⏰ Setting alarm for {user_id}: {time} - {label}")
    
    success = await db.create_alarm(user_id, time, label)
    if success:
        return f"Alarm set for {time} with label '{label}'."
    return "Failed to set alarm. Please check database connection."

@function_tool()
async def list_alarms(context: RunContext) -> str:
    """List all active alarms."""
    user_id = get_user_id(context)
    alarms = await db.get_active_alarms(user_id)
    
    if not alarms:
        return "You have no active alarms."
    
    return "Active Alarms:\n" + "\n".join(
        [f"- {a['alarm_time']}: {a['label']} (ID: {a['id']})" for a in alarms]
    )

@function_tool()
async def delete_alarm(context: RunContext, alarm_id: int) -> str:
    """Delete an alarm by ID."""
    user_id = get_user_id(context)
    success = await db.delete_alarm(user_id, alarm_id)
    
    if success:
        return f"Alarm {alarm_id} deleted."
    return f"Failed to delete alarm {alarm_id}."

# --- Reminders ---
@function_tool()
async def set_reminder(
    context: RunContext,
    text: str,
    time: str
) -> str:
    """Set a reminder."""
    user_id = get_user_id(context)
    success = await db.create_reminder(user_id, text, time)
    
    if success:
        return f"Reminder set: '{text}' for {time}."
    return "Failed to set reminder."

@function_tool()
async def list_reminders(context: RunContext) -> str:
    """List pending reminders."""
    user_id = get_user_id(context)
    reminders = await db.get_pending_reminders(user_id)
    
    if not reminders:
        return "You have no pending reminders."
    
    return "Pending Reminders:\n" + "\n".join(
        [f"- {r['remind_at']}: {r['text']}" for r in reminders]
    )

@function_tool()
async def delete_reminder(context: RunContext, reminder_id: int) -> str:
    """Delete a reminder (Not Implemented in DB yet, placeholder)."""
    return "Delete reminder not fully implemented in DB layer yet."

# --- Notes ---
@function_tool()
async def create_note(
    context: RunContext,
    title: str,
    content: str
) -> str:
    """Create a note."""
    user_id = get_user_id(context)
    success = await db.create_note(user_id, title, content)
    
    if success:
        return f"Note '{title}' created."
    return "Failed to create note."

@function_tool()
async def list_notes(context: RunContext) -> str:
    """List recent notes."""
    user_id = get_user_id(context)
    notes = await db.get_notes(user_id)
    
    if not notes:
        return "You have no notes."
    
    return "Recent Notes:\n" + "\n".join(
        [f"- {n['title']}: {n['content'][:50]}..." for n in notes]
    )

@function_tool()
async def read_note(context: RunContext, title: str) -> str:
    """Read a specific note (Placeholder)."""
    return "Reading specific note by title is not yet optimized in DB layer."

@function_tool()
async def delete_note(context: RunContext, title: str) -> str:
    """Delete a note (Placeholder)."""
    return "Delete note not implemented."

# --- Calendar (Placeholder) ---
@function_tool()
async def create_calendar_event(
    context: RunContext,
    title: str, 
    start_time: str, 
    end_time: str, 
    description: str = ""
) -> str:
    """Create calendar event."""
    return "Calendar events are not yet persisted to DB."

@function_tool()
async def list_calendar_events(context: RunContext) -> str:
    """List calendar events."""
    return "No calendar events found (DB not connected for calendar)."

@function_tool()
async def delete_calendar_event(context: RunContext, event_id: str) -> str:
    """Delete calendar event."""
    return "Calendar delete not implemented."
