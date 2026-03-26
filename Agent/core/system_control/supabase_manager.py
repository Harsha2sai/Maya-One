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


import json
from pathlib import Path

class LocalNoteStore:
    def __init__(self):
        self.path = Path("data/local_notes.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]")

    def _load(self):
        try:
            return json.loads(self.path.read_text())
        except:
            return []

    def _save(self, notes):
        self.path.write_text(json.dumps(notes, indent=2))

    def create_note(self, user_id, title, content):
        notes = self._load()
        note = {
            "user_id": user_id,
            "title": title,
            "content": content,
            "updated_at": time.time()
        }
        notes.append(note)
        self._save(notes)
        return True

    def get_notes(self, user_id, limit=10):
        notes = self._load()
        user_notes = [n for n in notes if n.get("user_id") == user_id]
        # Sort by updated_at desc
        user_notes.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        return user_notes[:limit]


class LocalTaskStore:
    def __init__(self):
        self.path = Path("data/local_tasks.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"alarms": [], "reminders": []}, indent=2))

    def _load(self) -> Dict[str, List[Dict[str, Any]]]:
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict):
                return {"alarms": [], "reminders": []}
            data.setdefault("alarms", [])
            data.setdefault("reminders", [])
            return data
        except Exception:
            return {"alarms": [], "reminders": []}

    def _save(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        self.path.write_text(json.dumps(data, indent=2))

    def create_alarm(self, user_id: str, alarm_time: str, label: str = "Alarm") -> bool:
        data = self._load()
        alarms = data["alarms"]
        next_id = (max([int(a.get("id", 0)) for a in alarms], default=0) + 1) if alarms else 1
        alarms.append(
            {
                "id": next_id,
                "user_id": user_id,
                "alarm_time": alarm_time,
                "label": label,
                "is_active": True,
                "created_at": time.time(),
            }
        )
        self._save(data)
        return True

    def get_active_alarms(self, user_id: str) -> List[Dict[str, Any]]:
        data = self._load()
        alarms = [a for a in data["alarms"] if a.get("user_id") == user_id and a.get("is_active", True)]
        alarms.sort(key=lambda x: str(x.get("alarm_time", "")))
        return alarms

    def delete_alarm(self, user_id: str, alarm_id: int) -> bool:
        data = self._load()
        original = len(data["alarms"])
        data["alarms"] = [
            a for a in data["alarms"]
            if not (a.get("user_id") == user_id and int(a.get("id", -1)) == int(alarm_id))
        ]
        self._save(data)
        return len(data["alarms"]) != original

    def create_reminder(self, user_id: str, text: str, remind_at: str) -> bool:
        data = self._load()
        reminders = data["reminders"]
        next_id = (max([int(r.get("id", 0)) for r in reminders], default=0) + 1) if reminders else 1
        reminders.append(
            {
                "id": next_id,
                "user_id": user_id,
                "text": text,
                "remind_at": remind_at,
                "is_completed": False,
                "created_at": time.time(),
            }
        )
        self._save(data)
        return True

    def get_pending_reminders(self, user_id: str) -> List[Dict[str, Any]]:
        data = self._load()
        reminders = [
            r for r in data["reminders"]
            if r.get("user_id") == user_id and not r.get("is_completed", False)
        ]
        reminders.sort(key=lambda x: str(x.get("remind_at", "")))
        return reminders

    def delete_reminder(self, user_id: str, reminder_id: int) -> bool:
        data = self._load()
        original = len(data["reminders"])
        data["reminders"] = [
            r for r in data["reminders"]
            if not (r.get("user_id") == user_id and int(r.get("id", -1)) == int(reminder_id))
        ]
        self._save(data)
        return len(data["reminders"]) != original


class SupabaseManager:
    """
    Manages asynchronous interactions with Supabase using asyncio.to_thread
    to avoid blocking the main event loop.
    """
    def __init__(self):
        self.client: Optional[Client] = None
        self.local_store = LocalNoteStore()
        self.local_tasks = LocalTaskStore()
        self._init_client()

    def _init_client(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not url or not key:
            logger.warning("⚠️ Supabase credentials not found. Using local fallback.")
            return

        # Check for feature flag
        enable_sync = os.getenv("ENABLE_SUPABASE_TASK_SYNC", "false").lower() == "true"
        if not enable_sync:
            logger.info("🛑 Supabase task sync disabled. Using local fallback for notes.")
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
            return None
        try:
            return await asyncio.to_thread(query_func)
        except Exception as e:
            logger.error(f"❌ Supabase Query Error: {e}")
            raise  # Re-raise for retry decorator

    # --- Alarms ---
    async def create_alarm(self, user_id: str, alarm_time: str, label: str = "Alarm") -> bool:
        if not self.client:
            return self.local_tasks.create_alarm(user_id, alarm_time, label)
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
        if not self.client:
            return self.local_tasks.get_active_alarms(user_id)
        def _query():
            return self.client.table("user_alarms").select("*")\
                .eq("user_id", user_id)\
                .eq("is_active", True)\
                .order("alarm_time")\
                .execute()
        
        result = await self._execute(_query)
        return result.data if result else []

    async def delete_alarm(self, user_id: str, alarm_id: int) -> bool:
        if not self.client:
            return self.local_tasks.delete_alarm(user_id, alarm_id)
        def _query():
            return self.client.table("user_alarms").delete()\
                .eq("user_id", user_id)\
                .eq("id", alarm_id)\
                .execute()
        
        result = await self._execute(_query)
        return bool(result and result.data)

    # --- Reminders ---
    async def create_reminder(self, user_id: str, text: str, remind_at: str) -> bool:
        if not self.client:
            return self.local_tasks.create_reminder(user_id, text, remind_at)
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
        if not self.client:
            return self.local_tasks.get_pending_reminders(user_id)
        def _query():
            return self.client.table("user_reminders").select("*")\
                .eq("user_id", user_id)\
                .eq("is_completed", False)\
                .order("remind_at")\
                .execute()
        
        result = await self._execute(_query)
        return result.data if result else []

    async def delete_reminder(self, user_id: str, reminder_id: int) -> bool:
        if not self.client:
            return self.local_tasks.delete_reminder(user_id, reminder_id)
        def _query():
            return self.client.table("user_reminders").delete()\
                .eq("user_id", user_id)\
                .eq("id", reminder_id)\
                .execute()

        result = await self._execute(_query)
        return bool(result is not None)

    # --- Notes ---
    async def create_note(self, user_id: str, title: str, content: str) -> str:
        if not self.client:
            self.local_store.create_note(user_id, title, content)
            return f"Note created: {title} - {content}"

        def _query():
            return self.client.table("user_notes").insert({
                "user_id": user_id,
                "title": title,
                "content": content
            }).execute()
        
        result = await self._execute(_query)
        if result and result.data:
             return f"Note created: {title} - {content}"
        return "Failed to create note."

    async def get_notes(self, user_id: str, limit: int = 10) -> List[Dict]:
        if not self.client:
            return self.local_store.get_notes(user_id, limit)

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
        if not self.client: return False
        def _query():
            return self.client.table("user_sessions").insert({
                "user_id": user_id,
                "livekit_room_id": room_id,
                "metadata": metadata
            }).execute()
        
        result = await self._execute(_query)
        return bool(result and result.data)
