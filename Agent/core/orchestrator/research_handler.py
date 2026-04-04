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
from dataclasses import dataclass, field
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