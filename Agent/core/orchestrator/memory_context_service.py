"""Memory retrieval policy and formatting helpers."""
from __future__ import annotations

import asyncio
import logging
import math
import os
import queue
import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.telemetry.runtime_metrics import RuntimeMetrics
from core.utils.small_talk_detector import is_small_talk

logger = logging.getLogger(__name__)

_PROFILE_RECALL_CLASSIFIER_PROMPT = """\
You are a strict query classifier.
Classify whether the user is asking about their OWN personal profile details.

Reply with exactly one word: profile OR general

profile = asks about their own saved identity/profile info (name, who they are, what you remember about them)
general = everything else, including coding/programming or questions about assistant identity

Examples:
what is my name -> profile
who am i -> profile
do you remember my name -> profile
what do you know about me -> profile
what is your name -> general
who are you -> general
what is my name in python -> general
my variable name is value, what is my name -> general
tell me more about him -> general

Query: {message}
Answer:"""


class MemoryContextService:
    """Owns memory retrieval policy without changing orchestrator call sites."""

    def __init__(self, *, owner: Any):
        self._owner = owner
        self._memory_query_type_cache: Dict[str, str] = {}

    @staticmethod
    def _extract_name_from_text(text: str) -> str:
        sample = str(text or "")
        if not sample:
            return ""
        profile_match = re.search(
            r"\buser profile fact:\s*name\s*=\s*([A-Za-z][A-Za-z0-9' -]{0,40})",
            sample,
            re.IGNORECASE,
        )
        if profile_match:
            return profile_match.group(1).strip().strip(".,!?;:\"'")
        name_match = re.search(
            r"\bmy name is\s+([A-Za-z][A-Za-z0-9' -]{0,40})",
            sample,
            re.IGNORECASE,
        )
        if name_match:
            return name_match.group(1).strip().strip(".,!?;:\"'")
        return ""

    def _extract_profile_name_from_memories(self, memories: List[Dict[str, Any]]) -> str:
        for item in memories or []:
            metadata = item.get("metadata") if isinstance(item, dict) else {}
            if isinstance(metadata, dict):
                if (
                    str(metadata.get("memory_kind", "")).lower() == "profile_fact"
                    and str(metadata.get("field", "")).lower() == "name"
                ):
                    value = str(metadata.get("value") or "").strip().strip(".,!?;:\"'")
                    if value:
                        return value
            text = str(item.get("text") if isinstance(item, dict) else "" or "")
            extracted = self._extract_name_from_text(text)
            if extracted:
                return extracted
        return ""

    def _extract_vector_name_from_memories(self, memories: List[Dict[str, Any]]) -> str:
        for item in memories or []:
            text = str(item.get("text") if isinstance(item, dict) else "" or "")
            extracted = self._extract_name_from_text(text)
            if extracted:
                return extracted
        return ""

    def _record_memory_retrieved(
        self,
        *,
        memories: List[Dict[str, Any]],
        session_id: str | None,
        origin: str,
        query_type: str,
        source: str,
    ) -> None:
        ranked_memories = self._rank_memories(memories or [], top_k=max(1, len(memories or [])))
        count = len(ranked_memories)
        if count <= 0:
            return
        RuntimeMetrics.increment("memory_hits_total", count)
        if source == "profile":
            RuntimeMetrics.increment("memory_hits_profile_total", count)
        elif source == "vector":
            RuntimeMetrics.increment("memory_hits_vector_total", count)
        top_score = float(ranked_memories[0].get("composite_score") or 0.0) if ranked_memories else 0.0
        logger.info(
            "memory_retrieved count=%s top_score=%.3f session=%s origin=%s query_type=%s source=%s",
            count,
            top_score,
            session_id or "none",
            origin,
            query_type,
            source,
        )

    def _is_profile_recall_candidate(self, text: str) -> bool:
        sample = str(text or "").strip().lower()
        if not sample:
            return False
        if self._owner._is_name_query(sample) or self._owner._is_creator_query(sample):
            return False
        markers = (
            "my name",
            "who am i",
            "remember me",
            "remember my name",
            "know my name",
            "know about me",
            "told you about me",
        )
        return any(marker in sample for marker in markers)

    async def classify_memory_query_type_async(
        self,
        user_input: str,
        *,
        route_hint: str = "",
        session_id: str | None = None,
    ) -> str:
        sample = re.sub(r"\s+", " ", str(user_input or "")).strip()
        if not sample:
            return "general"
        route_norm = str(route_hint or "").strip().lower()
        if route_norm == "identity" or self._owner._is_name_query(sample) or self._owner._is_creator_query(sample):
            return "general"
        if not self._is_profile_recall_candidate(sample):
            return "general"
        if re.search(r"\b(python|javascript|java|code|coding|function|variable|class|script|sql)\b", sample.lower()):
            return "general"

        cache_key = f"{session_id or 'none'}::{sample.lower()}"
        cached = self._memory_query_type_cache.get(cache_key)
        if cached:
            return cached
        llm = getattr(self._owner, "_router_llm_adapter", None)
        if llm is None:
            self._memory_query_type_cache[cache_key] = "general"
            return "general"
        try:
            prompt = _PROFILE_RECALL_CLASSIFIER_PROMPT.format(message=sample)
            raw = await llm.chat(prompt=prompt, max_tokens=5, temperature=0.0)
            label = "profile" if str(raw or "").strip().lower().startswith("profile") else "general"
            if label == "profile":
                label = "user_profile_recall"
            self._memory_query_type_cache[cache_key] = label
            return label
        except Exception:
            self._memory_query_type_cache[cache_key] = "general"
            return "general"

    async def _fetch_memories_async(
        self,
        query: str,
        *,
        k: int,
        user_id: str | None,
        session_id: str | None,
        origin: str,
    ) -> List[Dict[str, Any]]:
        if hasattr(self._owner.memory, "retrieve_relevant_memories_with_scope_fallback_async"):
            return await self._owner.memory.retrieve_relevant_memories_with_scope_fallback_async(
                query,
                k=k,
                user_id=user_id,
                session_id=session_id,
                origin=origin,
            )
        if hasattr(self._owner.memory, "retrieve_relevant_memories_async"):
            return await self._owner.memory.retrieve_relevant_memories_async(
                query,
                k=k,
                user_id=user_id,
                session_id=session_id,
                origin=origin,
            )
        return []

    async def resolve_profile_recall(
        self,
        user_input: str,
        *,
        user_id: str | None,
        session_id: str | None,
        origin: str = "chat",
    ) -> Tuple[Optional[str], str, str]:
        profile_memories = await self._fetch_memories_async(
            "User profile fact: name=",
            k=6,
            user_id=user_id,
            session_id=session_id,
            origin=origin,
        )
        profile_name = self._extract_profile_name_from_memories(profile_memories or [])

        vector_memories = await self._fetch_memories_async(
            user_input,
            k=5,
            user_id=user_id,
            session_id=session_id,
            origin=origin,
        )
        vector_name = self._extract_vector_name_from_memories(vector_memories or [])

        if profile_name:
            if vector_name and vector_name.lower() != profile_name.lower():
                logger.info(
                    "profile_vector_conflict_resolved=profile profile_name=%s vector_name=%s session=%s",
                    profile_name,
                    vector_name,
                    session_id or "none",
                )
            self._record_memory_retrieved(
                memories=profile_memories or [{"text": f"User profile fact: name={profile_name}"}],
                session_id=session_id,
                origin=origin,
                query_type="user_profile_recall",
                source="profile",
            )
            return profile_name, "profile", ""

        if vector_name:
            self._record_memory_retrieved(
                memories=vector_memories or [{"text": f"User: my name is {vector_name}"}],
                session_id=session_id,
                origin=origin,
                query_type="user_profile_recall",
                source="vector",
            )
            return vector_name, "vector", ""

        if profile_memories or vector_memories:
            return None, "", "profile_lookup_empty"
        return None, "", "retrieval_empty"

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

        probe_enabled = str(os.getenv("MAYA_MEMORY_PROBE", "false")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if probe_enabled:
            logger.info(
                "memory_probe_start query=%s session_id=%s user_id=%s origin=%s",
                str(user_input or "")[:80],
                session_id or "none",
                user_id or "none",
                origin,
            )

        try:
            memories = self._owner.memory.retrieve_relevant_memories(
                user_input,
                k=k,
                user_id=user_id,
                session_id=session_id,
                origin=origin,
            )
            if not memories:
                if probe_enabled:
                    self._log_memory_probe_counts()
                return []
            ranked_memories = self._rank_memories(memories or [], top_k=max(1, int(k or 5)))
            self._record_memory_retrieved(
                memories=ranked_memories,
                session_id=session_id,
                origin=origin,
                query_type="general",
                source="vector",
            )
            if probe_enabled:
                self._log_memory_probe_counts()
            return ranked_memories
        except Exception as exc:
            logger.error("Error retrieving memory context: %s", exc)
            return []

    def format_memory_context(self, memories: List[Dict[str, Any]]) -> str:
        if not memories:
            return ""
        formatted_lines: List[str] = []
        for memory in memories:
            if not isinstance(memory, dict):
                continue
            text = str(memory.get("text") or "").strip()
            if not text:
                continue
            relevance = float(memory.get("relevance_score") or 0.0)
            if relevance > 0:
                formatted_lines.append(f"- {text} (relevance={relevance:.2f})")
            else:
                formatted_lines.append(f"- {text}")
        formatted = "\n".join(formatted_lines)
        if not formatted:
            return ""
        return f"\nRelevant past memories:\n{formatted}\n"

    def _log_memory_probe_counts(self) -> None:
        """Emit minimal subsystem health signals for debugging empty retrievals."""
        try:
            retriever = getattr(self._owner.memory, "retriever", None)
            vector_store = getattr(retriever, "vector_store", None) if retriever else None
            keyword_store = getattr(retriever, "keyword_store", None) if retriever else None
            vector_count = vector_store.count() if vector_store and hasattr(vector_store, "count") else None
            keyword_count = keyword_store.count() if keyword_store and hasattr(keyword_store, "count") else None
            logger.info(
                "memory_probe_store_counts vector=%s keyword=%s",
                vector_count,
                keyword_count,
            )
        except Exception as probe_exc:
            logger.warning("memory_probe_failed error=%s", probe_exc)

    @staticmethod
    def _memory_created_at(memory: Dict[str, Any]) -> datetime | None:
        metadata = memory.get("metadata") if isinstance(memory, dict) else {}
        raw_created = ""
        if isinstance(metadata, dict):
            raw_created = str(metadata.get("created_at") or "")
        if not raw_created:
            raw_created = str(memory.get("created_at") or "")
        if not raw_created:
            return None
        candidate = raw_created.strip()
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    @staticmethod
    def _memory_importance(memory: Dict[str, Any]) -> float:
        metadata = memory.get("metadata") if isinstance(memory, dict) else {}
        value: Any = None
        if isinstance(metadata, dict):
            value = metadata.get("importance")
        if value is None:
            value = memory.get("importance")
        try:
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return 0.5

    @staticmethod
    def _memory_relevance(memory: Dict[str, Any]) -> float:
        """
        Normalize mixed retrieval metrics into [0,1].
        Prefers explicit fused/semantic scores when present.
        """
        try:
            if "relevance_score" in memory:
                return max(0.0, min(1.0, float(memory.get("relevance_score") or 0.0)))
        except Exception:
            pass
        for key in ("rrf_score", "score"):
            try:
                if key in memory:
                    return max(0.0, min(1.0, float(memory.get(key) or 0.0)))
            except Exception:
                continue
        try:
            distance = memory.get("distance")
            if distance is not None:
                return max(0.0, min(1.0, 1.0 - float(distance)))
        except Exception:
            pass
        try:
            rank_value = memory.get("rank")
            if rank_value is not None:
                rank = abs(float(rank_value))
                return max(0.0, min(1.0, 1.0 / (1.0 + rank)))
        except Exception:
            pass
        return 0.0

    def _rank_memories(self, memories: List[Dict[str, Any]], *, top_k: int) -> List[Dict[str, Any]]:
        """
        Weighted Memory Retrieval ranking:
        composite = 0.5*relevance + 0.3*recency + 0.2*importance
        """
        now = datetime.now(timezone.utc)
        scored: List[Dict[str, Any]] = []
        for item in memories:
            if not isinstance(item, dict):
                continue
            relevance = self._memory_relevance(item)
            created_at = self._memory_created_at(item)
            if created_at is None:
                recency = 0.5
            else:
                age_hours = max(0.0, (now - created_at).total_seconds() / 3600.0)
                recency = math.pow(0.995, age_hours)
            importance = self._memory_importance(item)
            composite = (0.5 * relevance) + (0.3 * recency) + (0.2 * importance)
            enriched = dict(item)
            enriched["relevance_score"] = round(relevance, 4)
            enriched["recency_score"] = round(recency, 4)
            enriched["importance_score"] = round(importance, 4)
            enriched["composite_score"] = round(composite, 4)
            scored.append(enriched)
        if not scored:
            return []
        scored.sort(key=lambda memory: float(memory.get("composite_score") or 0.0), reverse=True)
        min_threshold = max(0.0, float(os.getenv("MEMORY_MIN_COMPOSITE_SCORE", "0.25")))
        filtered = [memory for memory in scored if float(memory.get("composite_score") or 0.0) >= min_threshold]
        if not filtered:
            filtered = scored[: max(1, top_k)]
        return filtered[: max(1, top_k)]

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
        query_type: str = "general",
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

        profile_recall = str(query_type or "").strip().lower() == "user_profile_recall"
        skip_memory, skip_reason = self._owner._should_skip_memory(user_input, origin, routing_mode_type)
        if profile_recall:
            skip_memory = False
            skip_reason = "profile_recall"
        if skip_memory:
            logger.info(
                "🧠 memory_skipped=true memory_skip_reason=%s origin=%s routing_mode_type=%s query_type=%s",
                skip_reason,
                origin,
                routing_mode_type,
                query_type,
            )
            return ""

        if (not profile_recall) and origin != "voice" and self._owner._is_tool_focused_query(user_input):
            logger.info(
                "🧠 memory_skipped=true memory_skip_reason=tool_focused_chat origin=%s routing_mode_type=%s query_type=%s",
                origin,
                routing_mode_type,
                query_type,
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
            ranked_memories = self._rank_memories(memories or [], top_k=max_results)
            if ranked_memories:
                self._record_memory_retrieved(
                    memories=ranked_memories,
                    session_id=session_id,
                    origin=origin,
                    query_type=query_type,
                    source="vector",
                )
            memory_context = self._owner._format_memory_context(ranked_memories)
            elapsed_ms = max(0.0, (loop.time() - started) * 1000.0)
            self._owner._memory_timeout_count = 0
            logger.info(
                "🧠 memory_skipped=false memory_skip_reason=%s memory_budget_s=%s memory_ms=%.2f memory_results_count=%s origin=%s routing_mode_type=%s query_type=%s",
                skip_reason,
                "managed_by_retriever",
                elapsed_ms,
                len(ranked_memories),
                origin,
                routing_mode_type,
                query_type,
            )
            return memory_context
        except Exception as exc:
            logger.warning("⚠️ Async memory retrieval failed: %s", exc)
            return ""
