"""
ResearchHandler - Handles research route execution and context management.

Created: 2026-04-04 (P16-03)
Extracted from: AgentOrchestrator

This module handles:
- Research context storage and retrieval (session-scoped, TTL-guarded)
- Research pipeline execution (inline and background)
- Research result synthesis and voice output

Usage:
    handler = ResearchHandler(
        conversation_history_getter=lambda: orchestrator._conversation_history,
        spawn_background_task=orchestrator._spawn_background_task,
    )
    await handler.handle_research_route(message, user_id, tool_context, ...)
"""
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from core.communication import publish_agent_thinking, publish_tool_execution
from core.observability.trace_context import current_trace_id
from core.response.agent_response import AgentResponse

logger = logging.getLogger(__name__)


@dataclass
class ResearchContext:
    """Session-scoped research context with TTL."""
    subject: str
    query: str
    summary_sentence: str
    updated_at: float
    expires_at: float


class ResearchHandler:
    """
    Handles research route execution and context management.

    This class manages:
    1. Research context storage (session-scoped, TTL-guarded)
    2. Research pipeline execution
    3. Research result synthesis

    The handler is designed to be stateless - it receives conversation history
    and context through callbacks rather than storing state directly.
    """

    # Default TTL for research context (15 minutes)
    DEFAULT_CONTEXT_TTL_S = 900
    _RESEARCH_PRONOUN_TOKENS = {
        "him",
        "her",
        "he",
        "she",
        "it",
        "that",
        "this",
        "they",
        "them",
        "his",
        "their",
    }
    _RESEARCH_SUBJECT_STOPWORDS = {
        "i",
        "you",
        "we",
        "he",
        "she",
        "it",
        "they",
        "him",
        "her",
        "them",
        "this",
        "that",
        "who",
        "what",
        "when",
        "where",
        "why",
        "how",
        "tell",
        "about",
        "me",
        "us",
        "the",
        "a",
        "an",
    }
    _SUBJECT_FILLER_TOKENS = {
        "the",
        "a",
        "an",
        "recent",
        "latest",
        "ongoing",
        "current",
        "news",
        "about",
        "regarding",
        "between",
        "in",
        "on",
        "of",
    }

    def __init__(
        self,
        *,
        context_ttl_s: float = DEFAULT_CONTEXT_TTL_S,
        get_conversation_history: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        spawn_background_task: Optional[Callable[[Any], None]] = None,
        owner: Any = None,
    ):
        """
        Initialize the ResearchHandler.

        Args:
            context_ttl_s: TTL for research context in seconds
            get_conversation_history: Callback to get conversation history
            spawn_background_task: Callback to spawn background tasks
        """
        self._context_ttl_s = context_ttl_s
        self._get_conversation_history = get_conversation_history
        self._spawn_background_task = spawn_background_task
        self._owner = owner
        # Session-keyed research contexts
        self._last_research_contexts: Dict[str, Dict[str, Any]] = {}

    # -------------------------------------------------------------------------
    # Research Context Management
    # -------------------------------------------------------------------------

    def store_research_context(
        self,
        query: str,
        summary: str,
        *,
        session_key: str,
    ) -> None:
        """
        Store research context for session-scoped pronoun resolution.

        Args:
            query: The research query
            summary: The research summary
            session_key: Session identifier
        """
        now = time.time()
        subject = self._extract_subject_from_text(query) or self._extract_subject_from_text(summary)
        summary_sentence = self._extract_summary_sentence(summary)
        self._last_research_contexts[session_key] = {
            "subject": subject,
            "query": str(query or "").strip(),
            "summary_sentence": summary_sentence,
            "updated_at": now,
            "expires_at": now + self._context_ttl_s,
        }
        logger.info(
            "research_context_stored subject=%s ttl_s=%s",
            (subject or "unknown")[:80],
            int(self._context_ttl_s),
        )

    def get_active_research_context(
        self,
        session_key: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get active research context if not expired.

        Args:
            session_key: Session identifier

        Returns:
            Research context dict or None if expired/missing
        """
        context = self._last_research_contexts.get(session_key)
        if not context:
            return None
        expires_at = float(context.get("expires_at") or 0.0)
        if expires_at <= time.time():
            self._last_research_contexts.pop(session_key, None)
            return None
        return context

    def clear_research_context(self, session_key: str) -> None:
        """Clear research context for a session."""
        self._last_research_contexts.pop(session_key, None)

    def resolve_research_subject_from_context(
        self,
        *,
        research_context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        bootstrap_payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Resolve subject for pronoun follow-up from available contexts.

        Source order:
        1. Active research context
        2. History user entries with route=research
        3. History assistant entries with route=research
        4. Session continuity items
        5. Bootstrap topic summary / recent events
        """
        context = research_context or {}
        if context:
            candidate = str(context.get("subject") or "").strip()
            if candidate and not self._is_bad_subject(candidate):
                return candidate
            candidate = self._extract_subject_from_text(str(context.get("query") or ""))
            if candidate and not self._is_bad_subject(candidate):
                return candidate

        history: List[Dict[str, Any]]
        if conversation_history is not None:
            history = list(conversation_history)
        elif self._get_conversation_history:
            history = list(self._get_conversation_history() or [])
        else:
            history = []

        for item in reversed(history):
            if str(item.get("source") or "history") != "history":
                continue
            if str(item.get("role") or "").strip().lower() != "user":
                continue
            if str(item.get("route") or "") != "research":
                continue
            candidate = self._extract_subject_from_text(str(item.get("content") or ""))
            if candidate and not self._is_bad_subject(candidate):
                return candidate

        for item in reversed(history):
            if str(item.get("source") or "history") != "history":
                continue
            if str(item.get("role") or "").strip().lower() != "assistant":
                continue
            if str(item.get("route") or "") != "research":
                continue
            candidate = self._extract_subject_from_text(str(item.get("content") or ""))
            if candidate and not self._is_bad_subject(candidate):
                return candidate

        for item in reversed(history):
            if str(item.get("source") or "") != "session_continuity":
                continue
            candidate = self._extract_subject_from_text(str(item.get("content") or ""))
            if candidate and not self._is_bad_subject(candidate):
                return candidate

        payload = bootstrap_payload or {}
        topic_summary = str(payload.get("topic_summary") or "").strip()
        if topic_summary:
            candidate = self._extract_subject_from_text(topic_summary)
            if candidate and not self._is_bad_subject(candidate):
                return candidate

        recent_events = payload.get("recent_events") or []
        if isinstance(recent_events, list):
            for event in reversed(recent_events):
                if not isinstance(event, dict):
                    continue
                candidate = self._extract_subject_from_text(str(event.get("content") or ""))
                if candidate and not self._is_bad_subject(candidate):
                    return candidate

        return ""

    # -------------------------------------------------------------------------
    # Subject Extraction
    # -------------------------------------------------------------------------

    def _extract_subject_from_text(self, raw_text: str) -> str:
        """
        Extract a subject entity from query text.

        Uses capture patterns to find proper nouns or named entities.

        Args:
            raw_text: Input text to extract from

        Returns:
            Extracted subject, or empty string if not found
        """
        text = re.sub(r"\s+", " ", str(raw_text or "")).strip()
        if not text:
            return ""

        # Conflict-topic extraction for follow-ups like:
        # "war between iran and america", "iran america war", "US-Iran war".
        conflict_patterns = (
            r"\bwar\s+(?:between|in)\s+([a-z][a-z\s\-]{1,40}?)\s+(?:and|&)\s+([a-z][a-z\s\-]{1,40})(?:\b|$)",
            r"\b([a-z]{2,24})\s*(?:-|/)\s*([a-z]{2,24})\s+war\b",
            r"\b([a-z]{2,24})\s+([a-z]{2,24})\s+war\b",
        )
        for pattern in conflict_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            side_a = self._clean_entity_phrase(str(match.group(1) or ""))
            side_b = self._clean_entity_phrase(str(match.group(2) or ""))
            if side_a and side_b and side_a.lower() != side_b.lower():
                return f"{side_a} and {side_b} war"

        capture_patterns = (
            r"\bwho is (?:the )?(.+?)(?:\?|$)",
            r"\btell me about (.+?)(?:\?|$)",
            r"\bwhat about (.+?)(?:\?|$)",
            r"\bi asked you about (.+?)(?:\?|$)",
            r"\b(?:is|was)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b",
        )
        for pattern in capture_patterns:
            flags = re.IGNORECASE
            if pattern.startswith(r"\b(?:is|was)\s+([A-Z]"):
                flags = 0
            match = re.search(pattern, text, flags=flags)
            if not match:
                continue
            candidate = self._clean_subject_candidate(str(match.group(1) or ""))
            if not candidate:
                continue
            tokens = [token.lower() for token in re.findall(r"[A-Za-z']+", candidate)]
            if any(token in self._RESEARCH_PRONOUN_TOKENS for token in tokens):
                continue
            if candidate.lower() in self._RESEARCH_SUBJECT_STOPWORDS:
                continue
            if len(tokens) <= 10:
                return candidate

        named_candidates = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b", text)
        for candidate in named_candidates:
            cleaned = self._clean_subject_candidate(candidate)
            if not cleaned:
                continue
            if cleaned.lower() in self._RESEARCH_SUBJECT_STOPWORDS:
                continue
            if len(cleaned.split()) == 1 and len(cleaned) <= 3:
                continue
            return cleaned

        return ""

    def _clean_entity_phrase(self, phrase: str) -> str:
        tokens = [
            token
            for token in re.findall(r"[A-Za-z']+", str(phrase or "").lower())
            if token not in self._SUBJECT_FILLER_TOKENS and token not in {"war", "going"}
        ]
        if not tokens:
            return ""
        compact = " ".join(tokens[:4]).strip()
        if not compact:
            return ""
        return " ".join(part.capitalize() for part in compact.split())

    def _clean_subject_candidate(self, candidate: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(candidate or "")).strip(" .?!,;:")
        if not cleaned:
            return ""
        lowered = cleaned.lower()
        if "war going in between" in lowered:
            return ""
        cleaned = re.sub(r"^(?:the|a|an|about|regarding)\s+", "", cleaned, flags=re.IGNORECASE).strip()
        lowered = cleaned.lower()
        if not cleaned or lowered in self._RESEARCH_SUBJECT_STOPWORDS:
            return ""
        if re.fullmatch(r"(it|that|this|them|they|him|her)", lowered):
            return ""
        if re.search(r"\b(going in between|something|anything)\b", lowered):
            return ""
        tokens = re.findall(r"[A-Za-z']+", cleaned)
        if not tokens or len(tokens) > 12:
            return ""
        if cleaned.islower() and len(tokens) <= 5:
            cleaned = " ".join(token.capitalize() for token in tokens)
        return cleaned

    @staticmethod
    def _is_bad_subject(candidate: str) -> bool:
        """
        Check if a candidate subject should be rejected.

        Bad subjects include filesystem paths and common nouns.

        Args:
            candidate: Candidate subject string

        Returns:
            True if the subject should be rejected
        """
        if not candidate:
            return True
        lowered = candidate.strip().lower()
        if not lowered:
            return True
        # Avoid filesystem/location nouns from task requests
        bad_subjects = {"downloads", "download", "desktop", "documents", "folder", "file", "pdf"}
        if lowered in bad_subjects:
            return True
        if "/" in lowered or "\\" in lowered:
            return True
        if "war going in between" in lowered:
            return True
        if lowered in {"it", "that", "this", "them", "they", "him", "her"}:
            return True
        return False

    def _extract_summary_sentence(self, summary: str) -> str:
        """
        Extract the first sentence from a research summary.

        Args:
            summary: Full research summary

        Returns:
            First sentence, truncated if necessary
        """
        text = str(summary or "").strip()
        if not text:
            return ""
        text = re.sub(r"(?im)^\s*sources?\s*:.*$", "", text)
        text = re.sub(r"(?im)^\s*[-*•🔹✅🚀]\s*", "", text)
        text = re.sub(r"[*_`#>~]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return ""
        sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
        return sentence.rstrip(" ,;:")

    # -------------------------------------------------------------------------
    # Context Key Helpers
    # -------------------------------------------------------------------------

    def session_key_for_context(self, tool_context: Any) -> str:
        """
        Generate session key from tool context.

        Args:
            tool_context: Tool context with session info

        Returns:
            Session key string
        """
        session_id = getattr(tool_context, "session_id", None)
        if session_id:
            return str(session_id)
        # Fallback to room name
        room = getattr(tool_context, "room", None)
        if room:
            return getattr(room, "name", "default")
        return "default"

    # -------------------------------------------------------------------------
    # Pipeline Execution
    # -------------------------------------------------------------------------

    async def build_research_tasks_inline(
        self,
        query: str,
        *,
        enable_llm_planner: bool = False,
        smart_llm: Any = None,
    ) -> tuple[list[Any], str]:
        from core.research.research_planner import ResearchPlanner
        from core.research.research_task_builder import build_research_tasks

        tasks, fallback_query = build_research_tasks(query)
        if tasks and not enable_llm_planner:
            return tasks, fallback_query
        if not enable_llm_planner:
            return tasks, fallback_query

        role_llm = None
        try:
            from core.llm.role_llm import RoleLLM
            if smart_llm is not None:
                role_llm = RoleLLM(smart_llm)
        except Exception as e:
            logger.warning("inline_research_planner_role_llm_unavailable error=%s", e)

        planner = ResearchPlanner(role_llm=role_llm)
        llm_plan = await planner.plan(query)
        if llm_plan.tasks:
            return llm_plan.tasks, llm_plan.fallback_query or fallback_query
        return tasks, fallback_query

    def log_research_stage_metrics(
        self,
        *,
        query: str,
        plan_ms: int,
        search_ms: int,
        synth_ms: int,
        source_count: int,
        trace_id: str,
        enable_llm_planner: bool = False,
    ) -> None:
        total_ms = max(0, plan_ms + search_ms + synth_ms)
        logger.info(
            "research_pipeline_mode=inline_main llm_planner_enabled=%s query=%s",
            enable_llm_planner,
            query[:120],
            extra={"trace_id": trace_id},
        )
        logger.info(
            "research_stage_timing plan_ms=%s search_ms=%s synth_ms=%s total_ms=%s source_count=%s",
            plan_ms,
            search_ms,
            synth_ms,
            total_ms,
            source_count,
            extra={"trace_id": trace_id},
        )

    async def run_inline_research_pipeline(
        self,
        *,
        query: str,
        user_id: str,
        session_id: str,
        trace_id: str,
        enable_llm_planner: bool = False,
        smart_llm: Any = None,
        should_use_deep_voice: bool = False,
    ) -> Any:
        from core.research.research_models import ResearchResult
        from core.research.result_synthesizer import ResultSynthesizer
        from core.research.search_executor import SearchExecutor

        started = time.monotonic()
        plan_started = time.monotonic()
        tasks, fallback_query = await self.build_research_tasks_inline(
            query,
            enable_llm_planner=enable_llm_planner,
            smart_llm=smart_llm,
        )
        plan_ms = int(max(0.0, (time.monotonic() - plan_started) * 1000.0))

        search_started = time.monotonic()
        executor = SearchExecutor()
        sources = await executor.execute(tasks, fallback_query or query)
        search_ms = int(max(0.0, (time.monotonic() - search_started) * 1000.0))

        synth_started = time.monotonic()
        voice_mode = "deep" if should_use_deep_voice else "brief"

        if not sources and not executor.has_configured_premium_provider():
            synth_ms = int(max(0.0, (time.monotonic() - synth_started) * 1000.0))
            self.log_research_stage_metrics(
                query=query,
                plan_ms=plan_ms,
                search_ms=search_ms,
                synth_ms=synth_ms,
                source_count=0,
                trace_id=trace_id,
                enable_llm_planner=enable_llm_planner,
            )
            total_ms = int(max(0.0, (time.monotonic() - started) * 1000.0))
            msg = (
                "I can't produce a reliable research summary right now. "
                "Search provider is not configured."
            )
            return ResearchResult(
                summary=msg,
                voice_summary=msg,
                sources=[],
                query=query,
                trace_id=trace_id,
                duration_ms=total_ms,
                voice_mode=voice_mode,
            )

        role_llm = None
        try:
            from core.llm.role_llm import RoleLLM
            if smart_llm is not None:
                role_llm = RoleLLM(smart_llm)
        except Exception as e:
            logger.warning("inline_research_synth_role_llm_unavailable error=%s", e)

        synthesizer = ResultSynthesizer(role_llm=role_llm)
        display_summary, voice_summary = await synthesizer.synthesize(
            query,
            sources,
            voice_mode=voice_mode,
        )
        synth_ms = int(max(0.0, (time.monotonic() - synth_started) * 1000.0))

        self.log_research_stage_metrics(
            query=query,
            plan_ms=plan_ms,
            search_ms=search_ms,
            synth_ms=synth_ms,
            source_count=len(sources),
            trace_id=trace_id,
            enable_llm_planner=enable_llm_planner,
        )
        total_ms = int(max(0.0, (time.monotonic() - started) * 1000.0))
        return ResearchResult(
            summary=display_summary,
            voice_summary=voice_summary,
            sources=sources,
            query=query,
            trace_id=trace_id,
            duration_ms=total_ms,
            voice_mode=voice_mode,
        )

    # -------------------------------------------------------------------------
    # Route Execution (delegated from AgentOrchestrator)
    # -------------------------------------------------------------------------

    async def handle_research_route(
        self,
        *,
        message: str,
        user_id: str,
        tool_context: Any,
        query_rewritten: bool = False,
        query_ambiguous: bool = False,
        publish_agent_thinking_fn: Callable[..., Any] = publish_agent_thinking,
        publish_tool_execution_fn: Callable[..., Any] = publish_tool_execution,
    ) -> AgentResponse:
        """Run research in background and return immediate acknowledgement."""
        owner = self._owner
        if owner is None:
            raise RuntimeError("ResearchHandler owner is not configured")

        handoff_target = owner._consume_handoff_signal(
            target_agent="research",
            execution_mode="inline",
            reason="research_route_selected",
            context_hint=str(message or "")[:160],
        )
        handoff_request = owner._build_handoff_request(
            target_agent=handoff_target,
            message=message,
            user_id=user_id,
            execution_mode="inline",
            tool_context=tool_context,
            handoff_reason="research_route_selected",
        )
        handoff_result = await owner._handoff_manager.delegate(handoff_request)
        if handoff_result.status == "failed":
            logger.warning(
                "research_handoff_fallback trace_id=%s error_code=%s",
                handoff_request.trace_id,
                handoff_result.error_code,
            )

        session_id = (
            getattr(tool_context, "session_id", None)
            or owner._current_session_id
            or getattr(getattr(owner, "room", None), "name", None)
            or "console_session"
        )
        trace_id = (
            getattr(tool_context, "trace_id", None)
            or current_trace_id()
            or str(uuid.uuid4())
        )
        turn_id = str(uuid.uuid4())
        research_query = (owner._extract_user_message_segment(message) or message).strip()
        if not research_query:
            research_query = str(message or "").strip()

        room = getattr(tool_context, "room", None)
        active_session = getattr(owner, "_session", None) or getattr(owner, "session", None)
        background_kwargs = {
            "query": research_query,
            "user_id": user_id,
            "session_id": session_id,
            "trace_id": trace_id,
            "turn_id": turn_id,
            "room": room,
            "session": active_session,
            "task_id": getattr(tool_context, "task_id", None),
            "conversation_id": getattr(tool_context, "conversation_id", None),
        }

        if room is not None:
            await publish_agent_thinking_fn(room, turn_id, "searching")
            await publish_tool_execution_fn(
                room,
                turn_id,
                "web_search",
                "started",
                message="Searching the web for research context.",
                task_id=background_kwargs["task_id"],
                conversation_id=background_kwargs["conversation_id"],
            )

        if room is not None or active_session is not None:
            owner._spawn_background_task(self.run_research_background(**background_kwargs))
        else:
            await self.run_research_background(**background_kwargs)

        owner._append_conversation_history(
            "user",
            message,
            source="history",
            route="research",
        )

        logger.info(
            "research_dispatched_to_background",
            extra={
                "trace_id": trace_id,
                "query": research_query,
                "research_query_rewritten": query_rewritten,
                "research_query_ambiguous": query_ambiguous,
            },
        )

        return AgentResponse(
            display_text="",
            voice_text="",
            structured_data={
                "_routing_mode_type": "research_pending",
                "_interaction_mode": "silent_ack",
                "_suppress_assistant_output": True,
                "turn_id": turn_id,
            },
        )

    async def run_research_background(
        self,
        *,
        query: str,
        user_id: str,
        session_id: str,
        trace_id: str,
        turn_id: str,
        room: Any,
        session: Any,
        task_id: str | None = None,
        conversation_id: str | None = None,
        publish_tool_execution_fn: Callable[..., Any] = publish_tool_execution,
    ) -> None:
        """Background research task. Publishes result to Flutter when done."""
        owner = self._owner
        if owner is None:
            raise RuntimeError("ResearchHandler owner is not configured")

        from core.communication import publish_research_result

        try:
            research_result = await owner._run_inline_research_pipeline(
                query=query,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
            )

            self.store_research_context(
                query=query,
                summary=research_result.summary,
                session_key=session_id,
            )
            active = self.get_active_research_context(session_id)
            if active:
                owner._last_research_contexts[session_id] = dict(active)
            subject = self._extract_subject_from_text(query) or "the requested topic"
            summary_sentence = self._extract_summary_sentence(research_result.summary)
            history_summary = f"Research result: {subject}. {summary_sentence}".strip()
            owner._append_conversation_history(
                "assistant",
                history_summary,
                source="research_summary",
                route="research",
            )

            logger.info(
                "research_background_complete",
                extra={"trace_id": trace_id, "source_count": len(research_result.sources)},
            )

            if room is not None:
                await publish_tool_execution_fn(
                    room,
                    turn_id,
                    "web_search",
                    "finished",
                    message="Research context is ready.",
                    task_id=task_id,
                    conversation_id=conversation_id,
                )
                await publish_research_result(
                    room,
                    turn_id=turn_id,
                    query=query,
                    summary=research_result.summary,
                    sources=[s.to_dict() for s in research_result.sources],
                    trace_id=trace_id,
                    task_id=task_id,
                    conversation_id=conversation_id,
                )
            else:
                logger.info(
                    "research_result_console",
                    extra={"display": research_result.summary[:200] if research_result.summary else "(empty)"},
                )

            sanitized_voice, sanitize_mode = owner._sanitize_research_voice_for_tts(
                research_result.voice_summary,
                research_result.summary,
                voice_mode=str(getattr(research_result, "voice_mode", "brief") or "brief"),
            )
            logger.info(
                "research_voice_tts_sanitized mode=%s before_len=%d after_len=%d",
                sanitize_mode,
                len(research_result.voice_summary or ""),
                len(sanitized_voice or ""),
            )

            if sanitized_voice:
                logger.info("tts_voice_summary: %s", (sanitized_voice or "")[:120])
                logger.info(
                    "research_voice_speak turn_id=%s voice_summary_len=%d",
                    turn_id,
                    len(sanitized_voice or ""),
                )

                if session is not None:
                    if getattr(owner, "_turn_in_progress", False):
                        logger.info(
                            "research_voice_skipped_turn_active turn_id=%s",
                            turn_id,
                        )
                    else:
                        await session.say(
                            sanitized_voice,
                            allow_interruptions=True,
                        )
                else:
                    logger.info("research_voice_skipped reason=no_session turn_id=%s", turn_id)
        except Exception as exc:
            if room is not None:
                await publish_tool_execution_fn(
                    room,
                    turn_id,
                    "web_search",
                    "failed",
                    message="Research request failed before results were ready.",
                    task_id=task_id,
                    conversation_id=conversation_id,
                )
            logger.error(
                "research_background_error",
                extra={"trace_id": trace_id, "error": str(exc)},
            )
