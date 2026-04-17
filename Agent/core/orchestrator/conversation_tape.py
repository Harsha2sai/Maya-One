"""Canonical conversation tape for normalized turn events."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_QUESTION_PREFIXES = (
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "can",
    "could",
    "would",
    "should",
    "is",
    "are",
    "do",
    "does",
    "did",
)


@dataclass
class ConversationTapeEvent:
    role: str
    text: str
    route: str
    intent: str
    entities: List[str]
    topic: str
    source: str
    session_id: str
    turn_id: str
    timestamp: str
    extractor: str = "deterministic"
    extraction_confidence: float = 1.0

    def to_history_entry(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["content"] = payload.pop("text")
        return payload


class ConversationTape:
    """Bounded event tape with deterministic semantics and optional LLM backfill."""

    def __init__(
        self,
        *,
        event_cap: int = 240,
        llm_client: Any = None,
        enable_llm_backfill: bool = True,
    ) -> None:
        self._event_cap = max(20, int(event_cap))
        self._events: List[Dict[str, Any]] = []
        self._llm = llm_client
        self._enable_llm_backfill = bool(enable_llm_backfill and llm_client is not None)

    def append_event(
        self,
        *,
        role: str,
        text: str,
        source: str,
        route: Optional[str],
        intent: Optional[str],
        session_id: str,
        turn_id: str,
        timestamp: Optional[str] = None,
    ) -> ConversationTapeEvent:
        clean_text = re.sub(r"\s+", " ", str(text or "")).strip()
        if not clean_text:
            raise ValueError("conversation_tape_empty_text")

        source_name = str(source or "history").strip() or "history"
        route_name = self._normalize_route(route=route, source=source_name)

        entities = self._extract_entities(clean_text)
        topic = self._extract_topic(clean_text, entities)
        resolved_intent = (
            str(intent or "").strip().lower()
            or self._infer_intent(clean_text, route_name, source_name)
        )
        confidence = 0.9 if (entities or topic) else 0.45

        event = ConversationTapeEvent(
            role=str(role or "user").strip().lower() or "user",
            text=clean_text,
            route=route_name,
            intent=resolved_intent or "statement",
            entities=entities,
            topic=topic,
            source=source_name,
            session_id=str(session_id or "").strip(),
            turn_id=str(turn_id or "").strip(),
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            extractor="deterministic",
            extraction_confidence=confidence,
        )

        self._events.append(asdict(event))
        if len(self._events) > self._event_cap:
            self._events = self._events[-self._event_cap :]

        if self._enable_llm_backfill and confidence < 0.6:
            self._schedule_backfill(len(self._events) - 1)

        return event

    def history(
        self,
        *,
        session_id: str = "",
        limit: Optional[int] = None,
        route: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        route_filter = str(route or "").strip().lower()
        rows = self.events(session_id=session_id, limit=None)
        if route_filter:
            rows = [item for item in rows if str(item.get("route", "")).lower() == route_filter]
        if limit is not None and limit > 0:
            rows = rows[-int(limit) :]
        return [self._event_to_history(item) for item in rows]

    def events(
        self,
        *,
        session_id: str = "",
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        session_key = str(session_id or "").strip()
        rows = list(self._events)
        if session_key:
            rows = [item for item in rows if str(item.get("session_id") or "").strip() == session_key]
        if limit is not None and limit > 0:
            rows = rows[-int(limit) :]
        return [dict(item) for item in rows]

    @staticmethod
    def _event_to_history(event: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(event)
        payload["content"] = payload.pop("text", "")
        return payload

    @staticmethod
    def _normalize_route(*, route: Optional[str], source: str) -> str:
        direct = str(route or "").strip().lower()
        if direct:
            return direct
        source_l = str(source or "").strip().lower()
        if source_l in {"research_summary", "research_result"}:
            return "research"
        if source_l in {"task_step"}:
            return "task"
        if source_l in {"tool_output", "direct_action"}:
            return "action"
        return "chat"

    @staticmethod
    def _infer_intent(text: str, route: str, source: str) -> str:
        if str(source or "").lower() in {"tool_output", "direct_action", "task_step"}:
            return "action_result"
        lowered = str(text or "").strip().lower()
        if not lowered:
            return "statement"
        if lowered.startswith("/"):
            return "slash_command"
        if lowered.endswith("?") or lowered.split(" ", 1)[0] in _QUESTION_PREFIXES:
            if route == "research":
                return "research_query"
            return "question"
        if route == "research":
            return "research_statement"
        return "statement"

    @staticmethod
    def _extract_entities(text: str) -> List[str]:
        entities: List[str] = []
        for quoted in re.findall(r'"([^"]+)"', text):
            clean = re.sub(r"\s+", " ", str(quoted or "")).strip(" .?!,;:")
            if clean and clean not in entities:
                entities.append(clean)
        named = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b", text)
        for value in named:
            clean = re.sub(r"\s+", " ", str(value or "")).strip(" .?!,;:")
            if clean and clean not in entities:
                entities.append(clean)
        return entities[:8]

    @staticmethod
    def _extract_topic(text: str, entities: List[str]) -> str:
        if entities:
            return entities[0]
        lowered = str(text or "").strip()
        for pattern in (
            r"\babout\s+(.+?)(?:\?|$)",
            r"\bof\s+(.+?)(?:\?|$)",
            r"\bon\s+(.+?)(?:\?|$)",
        ):
            match = re.search(pattern, lowered, flags=re.IGNORECASE)
            if not match:
                continue
            candidate = re.sub(r"\s+", " ", str(match.group(1) or "")).strip(" .?!,;:")
            if candidate:
                return candidate
        return ""

    def _schedule_backfill(self, index: int) -> None:
        if os.getenv("PYTEST_CURRENT_TEST"):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._backfill_event(index))

    async def _backfill_event(self, index: int) -> None:
        if index < 0 or index >= len(self._events):
            return
        snapshot = dict(self._events[index])
        text = str(snapshot.get("text") or "").strip()
        if not text or snapshot.get("extraction_confidence", 1.0) >= 0.6:
            return

        prompt = (
            "Extract message semantics as compact JSON with keys "
            "intent(string), topic(string), entities(array[string]). "
            "Return JSON only.\n"
            f'Message: "{text}"\nJSON:'
        )
        try:
            response = await self._llm.chat(prompt, max_tokens=120, temperature=0.0)
            parsed = json.loads(str(response or "").strip())
            if not isinstance(parsed, dict):
                return

            intent = str(parsed.get("intent") or "").strip().lower()
            topic = str(parsed.get("topic") or "").strip()
            entities = parsed.get("entities")
            normalized_entities: List[str] = []
            if isinstance(entities, list):
                for item in entities:
                    value = re.sub(r"\s+", " ", str(item or "")).strip(" .?!,;:")
                    if value and value not in normalized_entities:
                        normalized_entities.append(value)

            current = self._events[index]
            if intent:
                current["intent"] = intent
            if topic:
                current["topic"] = topic
            if normalized_entities:
                current["entities"] = normalized_entities[:8]
            current["extractor"] = "hybrid_llm_backfill"
            current["extraction_confidence"] = max(
                float(current.get("extraction_confidence", 0.45)),
                0.7,
            )
        except Exception as exc:
            logger.debug("conversation_tape_llm_backfill_failed index=%s error=%s", index, exc)
