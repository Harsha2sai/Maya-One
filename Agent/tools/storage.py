import logging
from datetime import datetime, timedelta
from typing import Optional
from dateutil import parser
from livekit.agents import function_tool, RunContext
from supabase_manager import supabase_manager
from .base import get_user_id

logger = logging.getLogger(__name__)

# ============================================
# Alarm Tools
# ============================================

@function_tool()
async def set_alarm(
    context: RunContext,
    time: str,
    label: Optional[str] = None
) -> str:
    """Set an alarm for a specific time."""
    user_id = get_user_id(context)
    try:
        now = datetime.now()
        try:
            # Parse time relative to now for "in X minutes"
            if "in" in time.lower() and "minute" in time.lower():
                import re
                minutes = int(re.search(r'(\d+)', time).group(1))
                alarm_time = now + timedelta(minutes=minutes)
            else:
                alarm_time = parser.parse(time, fuzzy=True, default=now)
                # If parsed time is in the past, assume tomorrow
                if alarm_time < now:
                    alarm_time += timedelta(days=1)
        except Exception:
            return f"Could not understand time: {time}"

        result = await supabase_manager.create_alarm(user_id, alarm_time, label or "Alarm")
        
        if result:
            time_str = parser.parse(result['alarm_time']).strftime("%I:%M %p")
            return f"Alarm set for {time_str} - {result['label']}"
        return "Failed to save alarm to database."
        
    except Exception as e:
        logger.error(f"Error setting alarm: {e}")
        return f"Could not set alarm: {e}"

@function_tool()
async def list_alarms(
    context: RunContext,
    dummy: str = ""
) -> str:
    """List all active alarms."""
    user_id = get_user_id(context)
    alarms = await supabase_manager.get_alarms(user_id)
    
    if not alarms:
        return "You have no active alarms."
    
    response = f"You have {len(alarms)} alarm(s):\n"
    for alarm in alarms:
        dt = parser.parse(alarm['alarm_time'])
        time_str = dt.strftime("%I:%M %p on %b %d")
        response += f"• {time_str} - {alarm['label']} (ID: {alarm['id']})\n"
    return response.strip()

@function_tool()
async def delete_alarm(context: RunContext, alarm_id: int) -> str:
    """Delete an alarm by its ID."""
    user_id = get_user_id(context)
    success = await supabase_manager.delete_alarm(alarm_id, user_id)
    if success:
        return f"Deleted alarm {alarm_id}."
    return f"Could not find or delete alarm {alarm_id}."

# ============================================
# Reminder Tools
# ============================================

@function_tool()
async def set_reminder(
    context: RunContext,
    text: str,
    time: str
) -> str:
    """Set a reminder for a specific time."""
    user_id = get_user_id(context)
    try:
        now = datetime.now()
        try:
            if "in" in time.lower() and ("minute" in time.lower() or "hour" in time.lower()):
                import re
                match = re.search(r'(\d+)\s*(minute|hour)', time.lower())
                if match:
                    value = int(match.group(1))
                    unit = match.group(2)
                    if unit == "minute":
                        remind_time = now + timedelta(minutes=value)
                    else:
                        remind_time = now + timedelta(hours=value)
                else:
                    return f"Could not understand time: {time}"
            else:
                remind_time = parser.parse(time, fuzzy=True, default=now)
                if remind_time < now:
                    remind_time += timedelta(days=1)
        except Exception:
            return f"Could not understand time: {time}"

        result = await supabase_manager.create_reminder(user_id, text, remind_time)
        
        if result:
            time_str = parser.parse(result['remind_at']).strftime("%I:%M %p")
            return f"Reminder set for {time_str}: {text}"
        return "Failed to save reminder to database."
        
    except Exception as e:
        logger.error(f"Error setting reminder: {e}")
        return f"Could not set reminder: {e}"

@function_tool()
async def list_reminders(
    context: RunContext,
    dummy: str = ""
) -> str:
    """List all active reminders."""
    user_id = get_user_id(context)
    reminders = await supabase_manager.get_reminders(user_id)
    
    if not reminders:
        return "You have no active reminders."
    
    response = f"You have {len(reminders)} reminder(s):\n"
    for reminder in reminders:
        dt = parser.parse(reminder['remind_at'])
        time_str = dt.strftime("%I:%M %p on %b %d")
        status = "✓" if reminder.get('is_completed') else "○"
        response += f"{status} {time_str} - {reminder['text']} (ID: {reminder['id']})\n"
    return response.strip()

@function_tool()
async def delete_reminder(context: RunContext, reminder_id: int) -> str:
    """Delete a reminder by its ID."""
    user_id = get_user_id(context)
    success = await supabase_manager.delete_reminder(reminder_id, user_id)
    if success:
        return f"Deleted reminder {reminder_id}."
    return f"Could not find or delete reminder {reminder_id}."

# ============================================
# Notes Tools
# ============================================

@function_tool()
async def create_note(
    context: RunContext,
    content: str,
    title: Optional[str] = None
) -> str:
    """Create a new note."""
    user_id = get_user_id(context)
    title = title or f"Note {datetime.now().strftime('%m/%d %H:%M')}"
    
    result = await supabase_manager.create_note(user_id, title, content)
    if result:
        return f"Note saved: {title}"
    return "Failed to save note."

@function_tool()
async def list_notes(
    context: RunContext,
    dummy: str = ""
) -> str:
    """List all saved notes."""
    user_id = get_user_id(context)
    notes = await supabase_manager.get_notes(user_id)
    
    if not notes:
        return "You have no notes."
    
    response = f"You have {len(notes)} note(s):\n"
    for note in notes:
        preview = note['content'][:50] + "..." if len(note['content']) > 50 else note['content']
        response += f"• {note['title']} (ID: {note['id']}): {preview}\n"
    return response.strip()

@function_tool()
async def read_note(context: RunContext, note_id: int) -> str:
    """Read a specific note by its ID."""
    user_id = get_user_id(context)
    notes = await supabase_manager.get_notes(user_id)
    
    for note in notes:
        if note['id'] == note_id:
            return f"{note['title']}:\n{note['content']}"
    return f"Note {note_id} not found."

@function_tool()
async def delete_note(context: RunContext, note_id: int) -> str:
    """Delete a note by its ID."""
    user_id = get_user_id(context)
    success = await supabase_manager.delete_note(note_id, user_id)
    if success:
        return f"Deleted note {note_id}."
    return f"Could not find or delete note {note_id}."

# ============================================
# Calendar Tools
# ============================================

@function_tool()
async def create_calendar_event(
    context: RunContext,
    title: str,
    start_time: str,
    duration_minutes: int = 60,
    description: Optional[str] = None
) -> str:
    """Create a calendar event."""
    user_id = get_user_id(context)
    try:
        now = datetime.now()
        event_start = parser.parse(start_time, fuzzy=True, default=now)
        if event_start < now:
            event_start += timedelta(days=1)
        
        event_end = event_start + timedelta(minutes=duration_minutes)
        
        result = await supabase_manager.create_calendar_event(
            user_id, title, event_start, event_end, description
        )
        
        if result:
            time_str = event_start.strftime("%I:%M %p on %b %d")
            return f"Calendar event created: {title} at {time_str}"
        return "Failed to create calendar event."
        
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}")
        return f"Could not create event: {e}"

@function_tool()
async def list_calendar_events(
    context: RunContext,
    dummy: str = ""
) -> str:
    """List upcoming calendar events."""
    user_id = get_user_id(context)
    events = await supabase_manager.get_calendar_events(user_id)
    
    if not events:
        return "You have no upcoming calendar events."
    
    response = f"You have {len(events)} upcoming event(s):\n"
    for event in events:
        start = parser.parse(event['start_time'])
        time_str = start.strftime("%I:%M %p on %b %d")
        response += f"• {time_str} - {event['title']} (ID: {event['id']})\n"
    return response.strip()

@function_tool()
async def delete_calendar_event(context: RunContext, event_id: int) -> str:
    """Delete a calendar event by its ID."""
    user_id = get_user_id(context)
    success = await supabase_manager.delete_calendar_event(event_id, user_id)
    if success:
        return f"Deleted calendar event {event_id}."
    return f"Could not find or delete event {event_id}."
