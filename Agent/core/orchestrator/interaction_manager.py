"""Identity/small-talk and preference interaction helpers for AgentOrchestrator."""
from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any, Dict, List, Optional

from core.response.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class InteractionManager:
    """Owns conversational identity and preference capture helper logic."""

    def __init__(self, *, owner: Any):
        self._owner = owner

    def match_small_talk_fast_path(self, message: str) -> Optional[str]:
        text = str(message or "").strip().lower()
        if not text:
            return None

        if re.search(r"^\s*(hi|hello|hey)\b", text):
            return "Hello. I'm Maya. How can I help you today?"
        if "how are you" in text:
            return "I'm doing well and ready to help. What do you need?"
        if re.search(r"\b(thanks|thank you|cheers)\b", text):
            return "You're welcome."
        if re.search(r"\b(bye|goodbye|see you)\b", text):
            return "Goodbye."
        return None

    async def handle_identity_fast_path(
        self,
        *,
        message: str,
        user_id: str,
        origin: str,
    ) -> Any:
        del user_id
        logger.info("identity_fast_path_matched origin=%s", origin)
        logger.info("context_builder_memory_skipped reason=identity_fast_path")

        who_are_you = (
            "I'm Maya, your AI voice assistant, made by Harsha.",
            "My name is Maya. I'm a voice AI assistant created by Harsha.",
            "I'm Maya — a voice assistant built by Harsha to help you with research, tasks, system control, and conversation.",
        )
        who_made_you = (
            "I was made by Harsha.",
            "Harsha built me. I'm Maya, a voice AI assistant.",
            "My creator is Harsha. I'm Maya.",
        )
        what_can_you_do = (
            "I can help with web research, playing music, opening apps, managing files, setting reminders, running tasks, and general conversation. Just ask.",
            "I handle research, system control, media, tasks, and chat. What do you need?",
        )
        introduce_yourself = (
            "I'm Maya, a voice AI assistant made by Harsha. I can help with research, music, apps, files, tasks, and conversation.",
            "Hello — I'm Maya. Harsha built me to be your AI assistant for voice and chat. How can I help?",
        )
        generic_identity = ("I'm Maya, your AI assistant, made by Harsha.",)

        utterance_l = message.lower()
        if re.search(
            r"\bwho\s+(?:made|created|built|developed)\s+you\b|\byour\s+(?:creator|developer|maker)\b|\bwhat\s+(?:company|team)\s+(?:made|built)\s+you\b",
            utterance_l,
        ):
            responses = who_made_you
        elif re.search(r"\bwhat can you do\b|\byour (?:features|capabilities)\b|\bhow can you help\b", utterance_l):
            responses = what_can_you_do
        elif re.search(r"\bintroduce yourself\b", utterance_l):
            responses = introduce_yourself
        elif re.search(
            r"\bwho are you\b|\bwhat are you\b|\bwhat is your name\b|\byour name\b|\bare you an ai\b|\bare you a bot\b",
            utterance_l,
        ):
            responses = who_are_you
        else:
            responses = generic_identity

        response_text = random.choice(responses)
        return self._owner._tag_response_with_routing_type(
            ResponseFormatter.build_response(
                display_text=response_text,
                voice_text=response_text,
            ),
            "informational",
        )

    @staticmethod
    def is_malformed_short_request(message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return True
        words = re.findall(r"[a-z]{2,}", text)
        weird_tokens = len(re.findall(r"[\[\]\{\}]", text))
        punctuation = len(re.findall(r"[^\w\s]", text))
        if weird_tokens > 0 and len(words) <= 4:
            return True
        if len(text) <= 32 and punctuation >= 4 and len(words) <= 3:
            return True
        return False

    @staticmethod
    def is_conversational_query(message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False
        patterns = (
            r"\b(what(?:'s| is)\s+your\s+name|who\s+are\s+you|who\s+(?:made|created|built)\s+you|what\s+are\s+you)\b",
            r"\b(what can you do|how can you help)\b",
            r"\b(thanks|thank you|cheers)\b",
            r"\b(hi|hello|hey|good morning|good evening)\b",
            r"\b(bye|goodbye|see you)\b",
        )
        return any(re.search(p, text) for p in patterns)

    @staticmethod
    def is_name_query(message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False
        return bool(re.search(r"\b(what(?:'s| is)\s+your\s+name|who\s+are\s+you)\b", text))

    @staticmethod
    def is_creator_query(message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False
        return bool(re.search(r"\b(who\s+(?:made|created|built)\s+you|who\s+is\s+your\s+creator)\b", text))

    def is_identity_dominant_query(self, message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False
        if self.is_name_query(text) or self.is_creator_query(text):
            return True
        return bool(
            re.search(
                r"\b(who\s+are\s+you|what\s+are\s+you|tell me about yourself|introduce yourself)\b",
                text,
            )
        )

    def strip_identity_preamble_if_needed(self, user_query: str, raw_text: str) -> str:
        text = str(raw_text or "").strip()
        if not text or self.is_identity_dominant_query(user_query):
            return text
        parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
        if len(parts) == 2:
            first = parts[0].strip().lower()
            if "maya" in first and ("created by harsha" in first or "voice assistant" in first):
                return parts[1].strip()
        return text

    async def apply_action_state_carryover(self, message: str) -> str:
        text = re.sub(r"\s+", " ", str(message or "")).strip()
        if not text:
            return ""
        if not getattr(self._owner, "_action_state_carryover_enabled", False):
            return text

        store = getattr(self._owner, "_action_state_store", None)
        if store is None:
            return text

        session_key = self._owner._session_key_for_context()

        additive = await store.resolve_additive(session_key, text)
        if additive:
            return f"open {additive}"

        lowered = text.lower()
        if lowered in {"close them", "close it", "close that", "close this"}:
            last_app = store.latest_opened_app_sync(session_key)
            if last_app:
                return f"close {last_app}"

        continuation = await store.resolve_continuation(session_key, text)
        if continuation and "youtube" in lowered and re.search(r"\b(search|videos|songs|music)\b", lowered):
            return f"open youtube and search for {continuation}"

        return text

    @staticmethod
    def is_user_name_recall_query(message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False
        return bool(
            re.search(
                r"\b(what(?:'s| is)\s+my\s+name|do you know my name|what do you know about me|what have i told you about me)\b",
                text,
            )
        )

    @staticmethod
    def extract_name_from_memory_messages(messages: List[Any]) -> Optional[str]:
        name_pattern = re.compile(r"\bmy name is\s+([A-Za-z][A-Za-z0-9' -]{0,40})", re.IGNORECASE)
        profile_pattern = re.compile(
            r"\buser profile fact:\s*name\s*=\s*([A-Za-z][A-Za-z0-9' -]{0,40})",
            re.IGNORECASE,
        )
        for message in messages or []:
            source = ""
            content: Any = ""
            if isinstance(message, dict):
                source = str(message.get("source", "")).lower()
                content = message.get("content", "")
            else:
                source = str(getattr(message, "source", "")).lower()
                content = getattr(message, "content", "")
            if source != "memory" and "[memory" not in str(content).lower():
                continue
            content_text = content if isinstance(content, str) else str(content)
            match = name_pattern.search(content_text) or profile_pattern.search(content_text)
            if match:
                return match.group(1).strip().strip(".,!?;:\"'")
        return None

    async def lookup_profile_name_from_memory(
        self,
        *,
        user_id: str,
        session_id: str | None,
        origin: str = "chat",
    ) -> Optional[str]:
        try:
            retriever = getattr(self._owner.memory, "retrieve_relevant_memories_with_scope_fallback_async", None)
            if not callable(retriever):
                return None
            memories = await retriever(
                query="User profile fact: name=",
                user_id=user_id,
                session_id=session_id,
                origin=origin,
                k=6,
            )
        except Exception as e:
            logger.warning("profile_name_lookup_failed user_id=%s session_id=%s error=%s", user_id, session_id, e)
            return None

        profile_pattern = re.compile(
            r"\buser profile fact:\s*name\s*=\s*([A-Za-z][A-Za-z0-9' -]{0,40})",
            re.IGNORECASE,
        )
        for item in memories or []:
            meta = item.get("metadata") if isinstance(item, dict) else {}
            if isinstance(meta, dict):
                if str(meta.get("memory_kind", "")).lower() == "profile_fact" and str(meta.get("field", "")).lower() == "name":
                    value = str(meta.get("value") or "").strip().strip(".,!?;:\"'")
                    if value:
                        return value
            text = str(item.get("text") if isinstance(item, dict) else "" or "")
            match = profile_pattern.search(text)
            if match:
                return match.group(1).strip().strip(".,!?;:\"'")
        return None

    def queue_preference_update(self, user_id: str, key: str, value: Any, source: str) -> None:
        if not self._owner.preference_manager:
            return
        if not str(user_id or "").strip():
            return
        set_pref = getattr(self._owner.preference_manager, "set", None)
        if callable(set_pref):
            asyncio.create_task(set_pref(user_id, key, value))
            logger.info(
                "preference_implicit_update_queued user_id=%s key=%s value=%s source=%s",
                user_id,
                key,
                value,
                source,
            )
            return
        update_pref = getattr(self._owner.preference_manager, "update_preference", None)
        if callable(update_pref):
            asyncio.create_task(update_pref(user_id, key, value))
            logger.info(
                "preference_implicit_update_queued user_id=%s key=%s value=%s source=%s",
                user_id,
                key,
                value,
                source,
            )

    def queue_preference_extraction(self, user_text: str, user_id: str) -> None:
        if not self._owner.preference_manager:
            return
        extract = getattr(self._owner.preference_manager, "extract_from_text", None)
        if callable(extract) and str(user_text or "").strip():
            asyncio.create_task(extract(user_text, user_id))
