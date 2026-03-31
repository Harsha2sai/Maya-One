import logging
import os
import sqlite3
import asyncio
from datetime import datetime
from typing import Annotated, Optional
from livekit.agents import function_tool, RunContext
from .base import get_user_id
from core.system_control.supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

# Initialize Manager
db = SupabaseManager()


def _get_db_path() -> str:
    return os.getenv("MAYA_NOTES_DB_PATH", os.path.join("data", "notes.db"))


def _connect_sqlite(db_path: str) -> sqlite3.Connection:
    use_uri = db_path.startswith("file:")
    conn = sqlite3.connect(db_path, uri=use_uri, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


async def _ensure_notes_table(db_path: Optional[str] = None) -> None:
    db_path = db_path or _get_db_path()

    def _op() -> None:
        if not db_path.startswith("file:"):
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        with _connect_sqlite(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_notes_user_title ON notes(user_id, title)"
            )

    await asyncio.to_thread(_op)


async def _create_note_record(db_path: str, user_id: str, title: str, content: str) -> int:
    await _ensure_notes_table(db_path)

    def _op() -> int:
        with _connect_sqlite(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO notes(user_id, title, content) VALUES (?, ?, ?)",
                (user_id, title, content),
            )
            return int(cursor.lastrowid)

    return await asyncio.to_thread(_op)


async def _find_notes_by_title(db_path: str, user_id: str, title: str) -> list[sqlite3.Row]:
    await _ensure_notes_table(db_path)

    def _op() -> list[sqlite3.Row]:
        with _connect_sqlite(db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, title, content, created_at
                FROM notes
                WHERE user_id = ? AND title = ?
                ORDER BY id ASC
                """,
                (user_id, title),
            ).fetchall()
            return list(rows)

    return await asyncio.to_thread(_op)


async def _list_note_rows(db_path: str, user_id: str) -> list[sqlite3.Row]:
    await _ensure_notes_table(db_path)

    def _op() -> list[sqlite3.Row]:
        with _connect_sqlite(db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, title, content, created_at
                FROM notes
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 10
                """,
                (user_id,),
            ).fetchall()
            return list(rows)

    return await asyncio.to_thread(_op)


async def _delete_note_by_id(db_path: str, note_id: int) -> bool:
    await _ensure_notes_table(db_path)

    def _op() -> bool:
        with _connect_sqlite(db_path) as conn:
            cursor = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            return cursor.rowcount == 1

    return await asyncio.to_thread(_op)


async def _ensure_calendar_events_table(db_path: Optional[str] = None) -> None:
    db_path = db_path or _get_db_path()

    def _op() -> None:
        if not db_path.startswith("file:"):
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        with _connect_sqlite(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_calendar_events_user_start ON calendar_events(user_id, start_time, id)"
            )

    await asyncio.to_thread(_op)


async def _create_calendar_event_record(
    db_path: str,
    user_id: str,
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
) -> int:
    await _ensure_calendar_events_table(db_path)

    def _op() -> int:
        with _connect_sqlite(db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO calendar_events(user_id, title, start_time, end_time, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, title, start_time, end_time, description),
            )
            return int(cursor.lastrowid)

    return await asyncio.to_thread(_op)


async def _list_calendar_event_rows(db_path: str, user_id: str) -> list[sqlite3.Row]:
    await _ensure_calendar_events_table(db_path)

    def _op() -> list[sqlite3.Row]:
        with _connect_sqlite(db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, title, start_time, end_time, description, created_at
                FROM calendar_events
                WHERE user_id = ?
                ORDER BY start_time ASC, id ASC
                LIMIT 20
                """,
                (user_id,),
            ).fetchall()
            return list(rows)

    return await asyncio.to_thread(_op)


async def _delete_calendar_event_by_id(db_path: str, user_id: str, event_id: int) -> bool:
    await _ensure_calendar_events_table(db_path)

    def _op() -> bool:
        with _connect_sqlite(db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM calendar_events WHERE user_id = ? AND id = ?",
                (user_id, event_id),
            )
            return cursor.rowcount == 1

    return await asyncio.to_thread(_op)


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
        [f"- {r.get('remind_at')}: {r.get('text')} (ID: {r.get('id')})" for r in reminders]
    )

@function_tool()
async def delete_reminder(context: RunContext, reminder_id: Optional[int] = None) -> str:
    """Delete a reminder by ID (defaults to latest if no ID provided)."""
    user_id = get_user_id(context)
    target_id = reminder_id
    if target_id is None:
        reminders = await db.get_pending_reminders(user_id)
        if not reminders:
            return "You have no pending reminders to delete."

        def _reminder_rank(reminder: dict) -> float:
            created = reminder.get("created_at") or reminder.get("createdAt")
            if isinstance(created, (int, float)):
                return float(created)
            remind_at = reminder.get("remind_at") or reminder.get("remindAt") or ""
            try:
                return float(remind_at)
            except Exception:
                try:
                    return datetime.fromisoformat(str(remind_at)).timestamp()
                except Exception:
                    return 0.0

        latest = max(reminders, key=_reminder_rank)
        target_id = latest.get("id")
        if target_id is None:
            return "Unable to delete reminder: missing reminder ID."

    success = await db.delete_reminder(user_id, int(target_id))
    if success:
        return f"Reminder {target_id} deleted."
    return f"Failed to delete reminder {target_id}."

# --- Notes ---
@function_tool()
async def create_note(
    context: RunContext,
    title: str,
    content: str
) -> str:
    """Create a note."""
    user_id = get_user_id(context)
    db_path = _get_db_path()
    await _create_note_record(db_path, user_id, title, content)
    return f"Note '{title}' created."

@function_tool()
async def list_notes(context: RunContext) -> str:
    """List recent notes."""
    user_id = get_user_id(context)
    db_path = _get_db_path()
    notes = await _list_note_rows(db_path, user_id)
    if not notes:
        return "You have no notes."

    return "Recent Notes:\n" + "\n".join(
        [f"- {n['title']}: {n['content']}" for n in notes]
    )

@function_tool()
async def read_note(context: RunContext, title: str) -> str:
    """Read a specific note by exact title."""
    user_id = get_user_id(context)
    db_path = _get_db_path()
    matches = await _find_notes_by_title(db_path, user_id, title)
    if not matches:
        return f"No note found with title '{title}'."
    if len(matches) > 1:
        return (
            f"needs_followup: Found multiple notes titled '{title}'. "
            "Please specify which one."
        )
    note = matches[0]
    return f"Note '{note['title']}': {note['content']}"

@function_tool()
async def delete_note(context: RunContext, title: str) -> str:
    """Delete a specific note by exact title."""
    user_id = get_user_id(context)
    db_path = _get_db_path()
    matches = await _find_notes_by_title(db_path, user_id, title)
    if not matches:
        return f"No note found with title '{title}'."
    if len(matches) > 1:
        return (
            f"needs_followup: Found multiple notes titled '{title}'. "
            "Please specify which one."
        )
    deleted = await _delete_note_by_id(db_path, int(matches[0]["id"]))
    if deleted:
        return f"Deleted note '{title}'."
    return f"Failed to delete note '{title}'."

# --- Calendar ---
@function_tool()
async def create_calendar_event(
    context: RunContext,
    title: str, 
    start_time: str, 
    end_time: str, 
    description: str = ""
) -> str:
    """Create a calendar event."""
    user_id = get_user_id(context)
    db_path = _get_db_path()
    event_id = await _create_calendar_event_record(
        db_path=db_path,
        user_id=user_id,
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=description,
    )
    return f"Created calendar event '{title}' (ID: {event_id})."

@function_tool()
async def list_calendar_events(context: RunContext) -> str:
    """List upcoming calendar events."""
    user_id = get_user_id(context)
    db_path = _get_db_path()
    events = await _list_calendar_event_rows(db_path, user_id)
    if not events:
        return "No upcoming calendar events."

    lines = []
    for event in events:
        line = f"- {event['title']}: {event['start_time']} to {event['end_time']}"
        if event["description"]:
            line += f" ({event['description']})"
        lines.append(line)
    return "Upcoming events:\n" + "\n".join(lines)

@function_tool()
async def delete_calendar_event(context: RunContext, event_id: str) -> str:
    """Delete a calendar event by ID."""
    user_id = get_user_id(context)
    db_path = _get_db_path()
    try:
        event_id_int = int(str(event_id).strip())
    except (TypeError, ValueError):
        return f"No calendar event found with ID {event_id}."

    deleted = await _delete_calendar_event_by_id(db_path, user_id, event_id_int)
    if deleted:
        return f"Deleted calendar event {event_id_int}."
    return f"No calendar event found with ID {event_id}."
