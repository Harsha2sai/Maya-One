"""Media query resolution helpers backed by stored preferences."""
from __future__ import annotations

import logging
import re
from typing import Any

from core.utils.context_signal import get_music_query

logger = logging.getLogger(__name__)


class MediaResolver:
    """Owns generic music request detection and preference-based expansion."""

    def __init__(self, *, owner: Any):
        self._owner = owner

    @staticmethod
    def is_generic_music_request(message: str) -> bool:
        text = str(message or "").strip().lower()
        return bool(
            re.search(
                r"\b(play|start|put on)\b(?:\s+(?:some|any))?\s+\b(music|songs?)\b",
                text,
                re.IGNORECASE,
            )
        )

    async def resolve_media_query_from_preferences(self, message: str, user_id: str) -> str:
        if not self._owner.preference_manager:
            return message
        if not self.is_generic_music_request(message):
            return message

        get_pref = getattr(self._owner.preference_manager, "get_all", None)
        if not callable(get_pref):
            get_pref = getattr(self._owner.preference_manager, "get_preferences", None)
        if not callable(get_pref):
            return message

        try:
            prefs = await get_pref(user_id)
        except Exception as pref_err:
            logger.debug("media_preference_lookup_failed user_id=%s error=%s", user_id, pref_err)
            return message

        music_app = str((prefs or {}).get("music_app") or "").strip().lower()
        music_genre = str((prefs or {}).get("music_genre") or "").strip().lower()
        if not music_app or not music_genre:
            return message

        query = get_music_query(music_genre)
        logger.info("media_preference_resolved app=%s query=%s user_id=%s", music_app, query, user_id)
        return f"play {query} on {music_app}"
