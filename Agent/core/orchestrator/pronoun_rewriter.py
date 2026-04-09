"""
PronounRewriter - Rewrites pronoun-based follow-up queries with resolved subjects.

Created: 2026-04-04 (P16-02)
Extracted from: AgentOrchestrator._resolve_research_subject_from_context and
                AgentOrchestrator.rewrite_research_query_for_context

This module handles the "What about him?" -> "What about Microsoft?" transformation
for research follow-up queries. The rewriter resolves pronouns (he, she, it, that)
to their antecedent subjects from:
1. Recent research context (session-scoped, TTL-guarded)
2. Conversation history (user messages)
3. Research context stored in tool_context

Usage:
    rewriter = PronounRewriter()
    rewritten, changed, ambiguous = rewriter.rewrite(
        query="what about him",
        conversation_history=history,
        research_context=research_ctx,
    )
"""
import re
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PronounRewriter:
    """
    Rewrites pronoun-based follow-up queries with resolved subjects.

    This class consolidates pronoun resolution logic that was previously
    scattered across multiple call sites in AgentOrchestrator.

    The rewriter resolves pronouns (he, she, it, that, this, they, them)
    to their antecedent subjects from research context or conversation history.
    """

    # Pronouns that trigger rewriting
    PRONOUN_PATTERN = re.compile(
        r"\b(he|she|him|her|it|that|this|they|them|his|their)\b",
        flags=re.IGNORECASE,
    )

    # Follow-up phrases that may contain pronouns
    FOLLOWUP_PATTERN = re.compile(
        r"\b(tell me more|more information|more about|what about|and what|and who|what does he|what does she|what does it)\b",
        flags=re.IGNORECASE,
    )

    # Action-object patterns to skip (e.g., "save it", "download that")
    ACTION_OBJECT_PATTERN = re.compile(
        r"\b(save|write|put|export|send|move|copy|open|download|create|generate|make)\s+"
        r"(it|that|this|them|they)\b",
        flags=re.IGNORECASE,
    )

    # Bad subjects to avoid (filesystem paths, common nouns)
    BAD_SUBJECTS = {
        "downloads", "download", "desktop", "documents", "folder", "file", "pdf"
    }
    SUBJECT_FILLER_TOKENS = {
        "the",
        "a",
        "an",
        "recent",
        "latest",
        "ongoing",
        "current",
        "about",
        "regarding",
        "between",
        "in",
        "on",
    }

    # Patterns to extract subject from query text
    SUBJECT_CAPTURE_PATTERNS = (
        r"\bwho is (?:the )?(.+?)(?:\?|$)",
        r"\btell me about (.+?)(?:\?|$)",
        r"\bwhat about (.+?)(?:\?|$)",
        r"\bi asked you about (.+?)(?:\?|$)",
        r"\b(?:is|was)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b",
    )

    def rewrite(
        self,
        query: str,
        *,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        research_context: Optional[Dict[str, Any]] = None,
        tool_context: Any = None,
        history_route_filter: Optional[str] = None,
    ) -> Tuple[str, bool, bool]:
        """
        Rewrite a query by resolving pronouns to their antecedent subjects.

        Args:
            query: The input query potentially containing pronouns
            conversation_history: List of conversation turns with 'role' and 'content'/'source'
            research_context: Stored research context with 'subject', 'query', 'expires_at'
            tool_context: Optional tool context for session resolution

        Returns:
            Tuple of (rewritten_query, changed, ambiguous)
            - rewritten_query: The query with pronouns resolved (or original if no change)
            - changed: True if the query was rewritten
            - ambiguous: True if the pronoun couldn't be resolved
        """
        raw_query = re.sub(r"\s+", " ", str(query or "")).strip()
        if not raw_query:
            return "", False, True

        has_pronoun = bool(self.PRONOUN_PATTERN.search(raw_query))
        if not has_pronoun:
            return raw_query, False, False

        # Skip action-object queries (e.g., "save it", "download that")
        if self.ACTION_OBJECT_PATTERN.search(raw_query):
            logger.info(
                "pronoun_followup_rewrite_skipped reason=action_object query=%s",
                raw_query[:160],
            )
            return raw_query, False, False

        # Resolve subject from context
        subject = self._resolve_subject(
            research_context=research_context,
            conversation_history=conversation_history,
            tool_context=tool_context,
            history_route_filter=history_route_filter,
        )

        if not subject:
            return raw_query, False, True

        # Apply rewrite
        rewritten = self._apply_rewrite(raw_query, subject)
        if not rewritten:
            return raw_query, False, True

        changed = rewritten.lower() != raw_query.lower()
        if changed:
            logger.info(
                "pronoun_followup_rewrite original_query=%s rewritten_query=%s",
                raw_query[:160],
                rewritten[:160],
            )
        return rewritten, changed, False

    def should_check_rewrite(self, query: str) -> bool:
        """
        Quick check if a query might need pronoun rewriting.

        Use this before the full rewrite to skip unnecessary processing.

        Args:
            query: The input query

        Returns:
            True if the query contains pronouns or followup phrases
        """
        query = re.sub(r"\s+", " ", str(query or "")).strip()
        if not query:
            return False

        has_pronoun = bool(self.PRONOUN_PATTERN.search(query))
        has_followup = bool(self.FOLLOWUP_PATTERN.search(query))
        return has_pronoun or has_followup

    def _resolve_subject(
        self,
        research_context: Optional[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, Any]]],
        tool_context: Any = None,
        history_route_filter: Optional[str] = None,
    ) -> str:
        """
        Resolve the pronoun antecedent from available contexts.

        Priority:
        1. Research context (session-scoped, TTL-guarded)
        2. Conversation history (user messages, most recent first)

        Args:
            research_context: Stored research context
            conversation_history: Conversation history
            tool_context: Optional tool context

        Returns:
            Resolved subject string, or empty string if not found
        """
        # Source 1: Research context (TTL-guarded)
        if research_context:
            # Check TTL
            expires_at = float(research_context.get("expires_at") or 0.0)
            if expires_at > time.time():
                candidate = str(research_context.get("subject") or "").strip()
                if candidate and not self._is_bad_subject(candidate):
                    return candidate
                candidate = self._extract_subject_from_text(
                    str(research_context.get("query") or "")
                )
                if candidate and not self._is_bad_subject(candidate):
                    return candidate

        # Source 2: Conversation history
        if conversation_history:
            history = list(conversation_history)
            for item in reversed(history):
                if str(item.get("source") or "history") != "history":
                    continue
                if str(item.get("role") or "").strip().lower() != "user":
                    continue
                if history_route_filter is not None and str(item.get("route") or "") != history_route_filter:
                    continue
                # Try to extract subject from user message
                content = str(item.get("content") or "")
                candidate = self._extract_subject_from_text(content)
                if candidate and not self._is_bad_subject(candidate):
                    return candidate

        return ""

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

        for pattern in self.SUBJECT_CAPTURE_PATTERNS:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            candidate = self._clean_subject_candidate(match.group(1))
            if candidate and not self._is_bad_subject(candidate):
                return candidate

        return ""

    def _clean_entity_phrase(self, phrase: str) -> str:
        tokens = [
            token
            for token in re.findall(r"[A-Za-z']+", str(phrase or "").lower())
            if token not in self.SUBJECT_FILLER_TOKENS and token not in {"war", "going"}
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
        if lowered in {"it", "that", "this", "them", "they", "him", "her"}:
            return ""
        if not cleaned:
            return ""
        return cleaned

    def _is_bad_subject(self, candidate: str) -> bool:
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
        if lowered in self.BAD_SUBJECTS:
            return True
        if "/" in lowered or "\\" in lowered:
            return True
        if lowered in {"it", "that", "this", "them", "they", "him", "her"}:
            return True
        if "war going in between" in lowered:
            return True
        if re.search(r"\b(going in between|something|anything)\b", lowered):
            return True
        return False

    def _apply_rewrite(self, query: str, subject: str) -> str:
        """
        Apply pronoun-to-subject rewrite to a query.

        Args:
            query: Original query
            subject: Subject to substitute

        Returns:
            Rewritten query, or empty string if no rewrite applied
        """
        # Pattern 1: "tell me about him" -> "tell me about Microsoft"
        rewritten = re.sub(
            r"\b(tell me about|what about|who is|how about)\s+(he|she|him|her|it|that|this|they|them)\b",
            lambda m: f"{m.group(1)} {subject}",
            query,
            count=1,
            flags=re.IGNORECASE,
        )

        # Pattern 2: "who is he" -> "who is Microsoft"
        if rewritten == query:
            rewritten = re.sub(
                r"\b(he|she|him|her|it|that|this|they|them|his|their)\b",
                subject,
                query,
                count=1,
                flags=re.IGNORECASE,
            )

        rewritten = re.sub(r"\s+", " ", rewritten).strip()
        return rewritten


# Module-level singleton for convenience
_default_rewriter = None


def get_pronoun_rewriter() -> PronounRewriter:
    """Get the default PronounRewriter instance."""
    global _default_rewriter
    if _default_rewriter is None:
        _default_rewriter = PronounRewriter()
    return _default_rewriter
