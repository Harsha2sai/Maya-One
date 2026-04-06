"""Memory retrieval policy and formatting helpers."""
from __future__ import annotations

import asyncio
import logging
import os
import queue
import re
import threading
from typing import Any, Dict, List

from core.telemetry.runtime_metrics import RuntimeMetrics
from core.utils.small_talk_detector import is_small_talk

logger = logging.getLogger(__name__)


class MemoryContextService:
    """Owns memory retrieval policy without changing orchestrator call sites."""

    def __init__(self, *, owner: Any):
        self._owner = owner

    def retrieve_memories(
        self,
        user_input: str,
        k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
        origin: str = "chat",
    ) -> List[Dict[str, Any]]:
        if is_small_talk(user_input):
            logger.debug("Small talk detected, skipping memory retrieval for: %s...", user_input[:30])
            return []

        try:
            memories = self._owner.memory.retrieve_relevant_memories(
                user_input,
                k=k,
                user_id=user_id,
                session_id=session_id,
                origin=origin,
            )
            if not memories:
                return []
            RuntimeMetrics.increment("memory_hits_total")
            return memories
        except Exception as exc:
            logger.error("Error retrieving memory context: %s", exc)
            return []

    def format_memory_context(self, memories: List[Dict[str, Any]]) -> str:
        if not memories:
            return ""
        formatted = "\n".join([f"- {m['text']}" for m in memories if isinstance(m, dict) and m.get("text")])
        if not formatted:
            return ""
        return f"\nRelevant past memories:\n{formatted}\n"

    def retrieve_memory_context(
        self,
        user_input: str,
        k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
        origin: str = "chat",
    ) -> str:
        memories = self._owner._retrieve_memories(
            user_input,
            k=k,
            user_id=user_id,
            session_id=session_id,
            origin=origin,
        )
        return self._owner._format_memory_context(memories)

    async def run_sync_with_timeout(
        self,
        func: Any,
        *args: Any,
        timeout_s: float,
    ) -> Any:
        """Run a blocking fallback in a daemon thread without tying up the loop executor."""
        loop = asyncio.get_running_loop()
        result_queue: "queue.Queue[tuple[bool, Any]]" = queue.Queue(maxsize=1)

        def _runner() -> None:
            try:
                result_queue.put((True, func(*args)))
            except BaseException as exc:  # pragma: no cover - defensive wrapper
                result_queue.put((False, exc))

        threading.Thread(target=_runner, daemon=True).start()

        deadline = loop.time() + timeout_s
        while True:
            try:
                ok, payload = result_queue.get_nowait()
            except queue.Empty:
                if loop.time() >= deadline:
                    raise asyncio.TimeoutError()
                await asyncio.sleep(0.01)
                continue

            if ok:
                return payload
            raise payload

    @staticmethod
    def is_tool_focused_query(message: str) -> bool:
        text = (message or "").lower()
        keywords = (
            "time", "date", "today", "weather", "alarm", "reminder", "note", "calendar",
            "email", "search", "find", "tool", "use ", "what is", "what's", "tell me",
        )
        return any(keyword in text for keyword in keywords)

    def is_memory_relevant(self, text: str) -> bool:
        sample = (text or "").lower()
        return any(re.search(pattern, sample) for pattern in self._owner.CONVERSATIONAL_MEMORY_TRIGGERS)

    def is_recall_exclusion_intent(self, text: str) -> bool:
        sample = (text or "").lower()
        return any(re.search(pattern, sample) for pattern in self._owner.RECALL_EXCLUSION_PATTERNS)

    def should_skip_memory(
        self,
        text: str,
        origin: str,
        routing_mode_type: str,
    ) -> tuple[bool, str]:
        if self._owner._is_name_query(text) or self._owner._is_creator_query(text):
            return True, "capability_or_identity_query"

        if re.search(
            r"\b(introduce yourself|tell me about yourself|what can you do|what are your capabilities|are you an ai|are you a bot|what is maya|what are your features)\b",
            (text or "").lower(),
        ):
            return True, "capability_or_identity_query"

        if origin != "voice":
            return False, "not_voice"

        if routing_mode_type in ("fast_path", "direct_action"):
            return True, routing_mode_type

        if self._owner._is_memory_relevant(text):
            return False, "conversational"

        return True, "no_recall_trigger"

    async def retrieve_memory_context_async(
        self,
        user_input: str,
        *,
        origin: str = "chat",
        routing_mode_type: str = "informational",
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        if str(os.getenv("MAYA_DISABLE_MEMORY_RETRIEVAL", "false")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            logger.info(
                "🧠 memory_skipped=true memory_skip_reason=disabled origin=%s routing_mode_type=%s",
                origin,
                routing_mode_type,
            )
            return ""

        skip_memory, skip_reason = self._owner._should_skip_memory(user_input, origin, routing_mode_type)
        if skip_memory:
            logger.info(
                "🧠 memory_skipped=true memory_skip_reason=%s origin=%s routing_mode_type=%s",
                skip_reason,
                origin,
                routing_mode_type,
            )
            return ""

        if origin != "voice" and self._owner._is_tool_focused_query(user_input):
            logger.info(
                "🧠 memory_skipped=true memory_skip_reason=tool_focused_chat origin=%s routing_mode_type=%s",
                origin,
                routing_mode_type,
            )
            return ""

        loop = asyncio.get_running_loop()
        if loop.time() < self._owner._memory_disabled_until:
            logger.info(
                "🧠 memory_skipped=true memory_skip_reason=temporary_disable origin=%s routing_mode_type=%s",
                origin,
                routing_mode_type,
            )
            return ""

        voice_memory_max_results = max(1, int(os.getenv("VOICE_MEMORY_MAX_RESULTS", "2")))
        max_results = voice_memory_max_results if origin == "voice" else 5
        fallback_timeout_s = max(0.1, float(os.getenv("VOICE_MEMORY_TIMEOUT_S", "0.60"))) if origin == "voice" else 2.0
        started = loop.time()

        try:
            if hasattr(self._owner.memory, "retrieve_relevant_memories_with_scope_fallback_async"):
                memories = await self._owner.memory.retrieve_relevant_memories_with_scope_fallback_async(
                    user_input,
                    k=max_results,
                    user_id=user_id,
                    session_id=session_id,
                    origin=origin,
                )
            elif hasattr(self._owner.memory, "retrieve_relevant_memories_async"):
                memories = await self._owner.memory.retrieve_relevant_memories_async(
                    user_input,
                    k=max_results,
                    user_id=user_id,
                    session_id=session_id,
                    origin=origin,
                )
            else:
                try:
                    memories = await self._owner._run_sync_with_timeout(
                        self._owner._retrieve_memories,
                        user_input,
                        max_results,
                        user_id,
                        session_id,
                        origin,
                        timeout_s=fallback_timeout_s,
                    )
                except TypeError:
                    memories = await self._owner._run_sync_with_timeout(
                        self._owner._retrieve_memories,
                        user_input,
                        max_results,
                        timeout_s=fallback_timeout_s,
                    )
            memory_context = self._owner._format_memory_context(memories)
            elapsed_ms = max(0.0, (loop.time() - started) * 1000.0)
            self._owner._memory_timeout_count = 0
            logger.info(
                "🧠 memory_skipped=false memory_skip_reason=%s memory_budget_s=%s memory_ms=%.2f memory_results_count=%s origin=%s routing_mode_type=%s",
                skip_reason,
                "managed_by_retriever",
                elapsed_ms,
                len(memories),
                origin,
                routing_mode_type,
            )
            return memory_context
        except Exception as exc:
            logger.warning("⚠️ Async memory retrieval failed: %s", exc)
            return ""
