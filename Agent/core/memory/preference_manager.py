"""
Preference Manager - Learn and persist user preferences.
"""
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict

from core.system_control.supabase_manager import SupabaseManager

logger = logging.getLogger(__name__)

EXPLICIT_PREFERENCE_PATTERNS: dict[str, str] = {
    "music_app": r"\b(spotify|youtube music|youtube|vlc)\b",
    "music_genre": r"\bi (?:like|love|prefer|enjoy)\s+([a-z0-9\-\s]+(?:music|jazz|rock|pop|lo-fi|classical|hip hop))\b",
    "music_language": r"\b(telugu|hindi|tamil|kannada|english)\s+(?:songs|music)\b",
    "home_city": r"\bi(?:'m| am) (?:from|in|based in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
    "preferred_browser": r"\bi (?:use|prefer)\s+(firefox|chrome|brave|edge)\b",
}


class PreferenceManager:
    """Manages user preferences and learning."""

    def __init__(self, storage_path: str = "data/preferences"):
        self.db = SupabaseManager()
        self._storage_path = Path(storage_path)
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict[str, Any]] = {}

    def _safe_user_id(self, user_id: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_\-]", "_", str(user_id or "default"))

    def _user_file(self, user_id: str) -> Path:
        return self._storage_path / f"{self._safe_user_id(user_id)}.json"

    def _load_local_preferences(self, user_id: str) -> Dict[str, Any]:
        if user_id in self._cache:
            return dict(self._cache[user_id])
        path = self._user_file(user_id)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            prefs = payload if isinstance(payload, dict) else {}
            self._cache[user_id] = dict(prefs)
            return dict(prefs)
        except Exception as err:
            logger.warning("⚠️ Failed to read local preferences for %s: %s", user_id, err)
            return {}

    def _save_local_preferences(self, user_id: str, prefs: Dict[str, Any]) -> None:
        safe_prefs = dict(prefs or {})
        self._cache[user_id] = safe_prefs
        try:
            self._user_file(user_id).write_text(
                json.dumps(safe_prefs, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as err:
            logger.warning("⚠️ Failed to persist local preferences for %s: %s", user_id, err)

    async def get_preferences(self, user_id: str) -> Dict[str, Any]:
        """Retrieve user preferences from Supabase, with local fallback."""
        if user_id in self._cache:
            return dict(self._cache[user_id])

        if self.db.client:
            try:
                result = await self.db._execute(
                    lambda: self.db.client.table("user_profiles")
                    .select("preferences")
                    .eq("id", user_id)
                    .single()
                    .execute()
                )
                if result and hasattr(result, "data") and result.data:
                    prefs = result.data.get("preferences", {}) or {}
                    if isinstance(prefs, dict):
                        self._save_local_preferences(user_id, prefs)
                        logger.info("📋 Retrieved preferences for user %s", user_id)
                        return dict(prefs)
            except Exception as e:
                logger.warning("⚠️ Failed to retrieve preferences from Supabase: %s", e)

        return self._load_local_preferences(user_id)

    async def get_all(self, user_id: str) -> Dict[str, Any]:
        """Compatibility helper for orchestration call sites."""
        return await self.get_preferences(user_id)

    async def update_preference(
        self,
        user_id: str,
        key: str,
        value: Any,
    ) -> bool:
        """Update a specific preference."""
        current_prefs = await self.get_preferences(user_id)
        current_prefs[key] = value
        self._save_local_preferences(user_id, current_prefs)

        if not self.db.client:
            logger.info("✅ Updated preference '%s' for user %s (local)", key, user_id)
            return True

        try:
            result = await self.db._execute(
                lambda: self.db.client.table("user_profiles")
                .update({"preferences": current_prefs})
                .eq("id", user_id)
                .execute()
            )
            if result:
                logger.info("✅ Updated preference '%s' for user %s", key, user_id)
                return True
            return False
        except Exception as e:
            logger.error("❌ Failed to update preference in Supabase, kept local copy: %s", e)
            return True

    async def set(self, user_id: str, key: str, value: Any) -> bool:
        """Compatibility alias used by orchestration fast-path hooks."""
        return await self.update_preference(user_id, key, value)

    async def learn_from_interaction(
        self,
        user_id: str,
        interaction_type: str,
        data: Dict[str, Any],
    ) -> bool:
        """
        Learn from user interactions to improve personalization.

        Examples:
        - interaction_type: "voice_command_preference"
        - interaction_type: "tool_usage_pattern"
        - interaction_type: "communication_style"
        """
        prefs = await self.get_preferences(user_id)
        learning_key = f"learned_{interaction_type}"
        if learning_key not in prefs:
            prefs[learning_key] = []
        prefs[learning_key].append(data)
        prefs[learning_key] = prefs[learning_key][-10:]
        self._save_local_preferences(user_id, prefs)

        if not self.db.client:
            logger.info("🧠 Learned from %s for user %s (local)", interaction_type, user_id)
            return True

        try:
            result = await self.db._execute(
                lambda: self.db.client.table("user_profiles")
                .update({"preferences": prefs})
                .eq("id", user_id)
                .execute()
            )
            if result:
                logger.info("🧠 Learned from %s for user %s", interaction_type, user_id)
                return True
            return False
        except Exception as e:
            logger.error("❌ Failed to learn from interaction in Supabase, kept local copy: %s", e)
            return True

    async def extract_from_text(self, text: str, user_id: str) -> None:
        if not str(text or "").strip():
            return
        for pref_key, pattern in EXPLICIT_PREFERENCE_PATTERNS.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            value = match.group(1).strip().lower()
            await self.set(user_id, pref_key, value)
            logger.info("preference_extracted key=%s value=%s user_id=%s", pref_key, value, user_id)

    async def get_communication_style(self, user_id: str) -> str:
        """Get preferred communication style (formal, casual, technical, etc.)."""
        prefs = await self.get_preferences(user_id)
        return prefs.get("communication_style", "friendly")

    async def get_voice_settings(self, user_id: str) -> Dict[str, Any]:
        """Get voice-related preferences (speed, pitch, language, etc.)."""
        prefs = await self.get_preferences(user_id)
        return prefs.get(
            "voice_settings",
            {
                "language": "en",
                "speed": 1.0,
                "voice_id": "default",
            },
        )
