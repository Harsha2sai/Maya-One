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
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

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

    def __init__(
        self,
        *,
        context_ttl_s: float = DEFAULT_CONTEXT_TTL_S,
        get_conversation_history: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        spawn_background_task: Optional[Callable[[Any], None]] = None,
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

        capture_patterns = (
            r"\bwho is (?:the )?(.+?)(?:\?|$)",
            r"\btell me about (.+?)(?:\?|$)",
            r"\bwhat about (.+?)(?:\?|$)",
            r"\bi asked you about (.+?)(?:\?|$)",
            r"\b(?:is|was)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b",
        )
        for pattern in capture_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            candidate = match.group(1).strip()
            if candidate and not self._is_bad_subject(candidate):
                return candidate

        return ""

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
        return False

    def _extract_summary_sentence(self, summary: str) -> str:
        """
        Extract the first sentence from a research summary.

        Args:
            summary: Full research summary

        Returns:
            First sentence, truncated if necessary
        """
        if not summary:
            return ""
        # Split on sentence boundaries
        sentences = re.split(r"[.!?]\s+", summary)
        if sentences:
            first = sentences[0].strip()
            # Truncate to reasonable length
            if len(first) > 200:
                first = first[:197] + "..."
            return first
        return ""

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
