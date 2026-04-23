import logging
import json
import os
import re
from typing import Any, Dict, List

from core.orchestrator.fact_classifier import FactClassifier

logger = logging.getLogger(__name__)


class AgentRouter:
    ALLOWED_KEYS = {"identity", "media_play", "research", "system", "scheduling", "chat"}
    _USER_MEMORY_PATTERNS = (
        r"\bdo you know my name\b",
        r"\bwhat do you know about me\b",
        r"\bdo you remember\b",
        r"\bwhat have i told you\b",
        r"\bremember when i said\b",
        r"\bmy name is\b",
        r"\bwhat(?:'s| is)\s+my\s+name\b",
        r"\bremember my\b",
    )
    _IDENTITY_PATTERNS = (
        r"\bwhat(?:'s| is)\s+your\s+name\b",
        r"\bwho are you\b",
        r"\bwhat can you do\b",
        r"\bare you an ai\b",
        r"\btell me about yourself\b",
        r"\bwho\s+(?:made|created|built|developed)\s+you\b",
        r"\bwho\s+(?:is\s+)?your\s+(?:creator|developer|maker|author)\b",
        r"\bintroduce\s+yourself\b",
        r"\bwhat\s+are\s+you\b",
        r"\bwhere\s+(?:do\s+you\s+come\s+from|are\s+you\s+from)\b",
        r"\bwhat\s+(?:company|organization|team)\s+(?:made|built|created)\s+you\b",
    )
    _NOTE_PATTERNS = (
        r"\bread\s+my\s+note\b",
        r"\bdelete\s+my\s+note\b",
        r"\bshow\s+my\s+note\b",
        r"\blist\s+my\s+notes\b",
    )
    _RESEARCH_FRESHNESS_PATTERNS = (
        r"\bwho is (?:the )?(?:current )?(?:ceo|cto|cfo|president|founder|head|prime minister|chancellor|governor|mayor)\b",
        r"\bcurrent (?:ceo|cto|cfo|leader|president|head|prime minister|chancellor|governor|mayor)\b",
        r"\b(?:do you know|tell me about|know about)\s+(?:the\s+)?(?:current\s+)?(?:ceo|cto|cfo|president|founder|head|prime minister|chancellor|governor|mayor)\b",
        r"\bwho (?:runs|leads|owns|heads)\b",
        r"\b(latest|recent|today|right now|this week)\b",
        r"\bnews\b",
    )

    _RESEARCH_INTENT_PATTERNS = (
        r"\bweb\s*search\b",
        r"\bsearch (?:the )?web\b",
        r"\bsearch for\b",
        r"\blook up\b",
        r"\bfind (?:information|news|details)\b",
        r"\bgoogle (?:for|this|that|it|search|look up)\b",
        r"\bwhat(?:'s| is)\s+happening\b",
    )
    _SYSTEM_INTENT_PATTERNS = (
        r"\bpc control\b",
        r"\bdesktop (?:control|operation|ops)\b",
        r"\bopen (?:the )?(?:app|application|browser|folder|file|settings|terminal)\b",
        r"\bclose (?:the )?(?:app|application|window|browser)\b",
        r"\bclick\b",
        r"\bdouble click\b",
        r"\bright click\b",
        r"\bscroll\b",
        r"\btype\b",
        r"\bpress (?:enter|tab|escape|esc)\b",
        r"\btake (?:a )?screenshot\b",
        r"\btake (?:a )?(?:photo|photograph|picture)\b",
        r"\bcapture (?:a )?(?:photo|photograph|picture)\b",
        r"\blaunch\b",
    )
    _MEDIA_PLAY_PATTERNS = (
        r"\bplay\b",
        r"\bput on\b",
        r"\bstart playing\b",
        r"\bnext\s+(?:track|song|video)\b",
        r"\bskip\b",
        r"\bpause\b",
        r"\bresume\b",
    )
    _SCHEDULING_PATTERNS = (
        r"\bremind me\b",
        r"\bset (?:a )?reminder\b",
        r"\bwhat(?:'s| is)\s+(?:my|the)\s+reminder\b",
        r"\bwhat reminder did (?:i|you) set\b",
        r"\bwhich reminder\b",
        r"\bwhen is (?:my|the) reminder\b",
        r"\blist reminders\b",
        r"\bshow reminders\b",
        r"\bdelete reminder\b",
        r"\bset (?:an )?alarm\b",
        r"\bwhat(?:'s| is)\s+(?:my|the)\s+alarm\b",
        r"\blist alarms\b",
        r"\bshow alarms\b",
        r"\bdelete alarm\b",
        r"\bcalendar event\b",
        r"\bcalendar\b",
    )
    _TASK_LIST_PATTERNS = (
        r"\blist (?:my )?tasks\b",
        r"\bshow (?:my )?tasks\b",
        r"\bget (?:my )?tasks\b",
        r"\bmy tasks\b",
    )
    _PRONOUN_FOLLOWUP_PATTERNS = (
        r"\btell me more about (him|her|them|it|that)\b",
        r"\bmore about (him|her|them|it|that)\b",
        r"\bwhat about (him|her|them|it|that)\b",
    )

    def __init__(self, llm_client: Any):
        self._llm = llm_client
        self._fact_classifier = FactClassifier(llm_client)
        self._depth: Dict[str, int] = {}
        self.MAX_DEPTH = 3
        self._last_route: Dict[str, str] = {}
        self._pending_clarifications: Dict[str, str] = {}
        self._llm_router_shadow = str(
            os.getenv("LLM_ROUTER_SHADOW", "true")
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._llm_router_active = str(
            os.getenv("LLM_ROUTER_ACTIVE", "false")
        ).strip().lower() in {"1", "true", "yes", "on"}

    def consume_pending_clarification(self, user_id: str) -> str:
        key = str(user_id or "anonymous")
        return str(self._pending_clarifications.pop(key, "") or "")

    @staticmethod
    def _is_ambiguous_followup_query(utterance_l: str) -> bool:
        text = str(utterance_l or "").strip().lower()
        return bool(
            re.search(r"^\s*what(?:'s| is)\s+(?:the\s+)?reason\b", text)
            or text in {"why", "why?", "what about that", "what about it"}
        )

    @staticmethod
    def _message_role(message: Any) -> str:
        if isinstance(message, dict):
            return str(message.get("role") or "").strip().lower()
        return str(getattr(message, "role", "") or "").strip().lower()

    @staticmethod
    def _message_content(message: Any) -> Any:
        if isinstance(message, dict):
            return message.get("content")
        return getattr(message, "content", None)

    @staticmethod
    def _flatten_content(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                    continue
                if isinstance(part, dict):
                    text_value = part.get("text") or part.get("content") or ""
                    if text_value:
                        parts.append(str(text_value))
                    continue
                text_value = getattr(part, "text", None)
                if text_value:
                    parts.append(str(text_value))
                    continue
                part_content = getattr(part, "content", None)
                if part_content:
                    parts.append(str(part_content))
            return " ".join(p.strip() for p in parts if str(p).strip()).strip()
        if isinstance(content, dict):
            text_value = content.get("text") or content.get("content") or ""
            return str(text_value).strip()
        return str(content).strip()

    def _last_assistant_message_text(self, chat_ctx: List[Any]) -> str:
        for message in reversed(chat_ctx):
            if self._message_role(message) != "assistant":
                continue
            text = self._flatten_content(self._message_content(message))
            if text:
                return text
        return ""

    @staticmethod
    def _extract_subject_candidate(text: str) -> str:
        content = str(text or "").strip()
        if not content:
            return ""
        patterns = (
            r"\b(?:about|regarding|on)\s+([A-Z][A-Za-z0-9 .'-]{2,80})",
            r"\b(?:who is|what is)\s+([A-Z][A-Za-z0-9 .'-]{2,80})",
        )
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1).strip(" .,!?:;\"'")
        return ""

    def _resolve_subject_from_history(self, recent_history: List[Any]) -> str:
        for item in reversed(recent_history or []):
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "")
            if not content:
                continue
            route = str(item.get("route") or "").strip().lower()
            source = str(item.get("source") or "").strip().lower()
            if route == "research" or source == "tool_output":
                subject = self._extract_subject_candidate(content)
                if subject:
                    return subject
        return ""

    @staticmethod
    def _looks_like_short_followup(utterance_l: str) -> bool:
        if "?" in utterance_l:
            return False
        words = re.findall(r"\b[\w'-]+\b", utterance_l)
        if not words or len(words) > 8:
            return False

        direct_followups = {
            "yes",
            "no",
            "ok",
            "okay",
            "sure",
            "yep",
            "nope",
            "right",
            "correct",
            "exactly",
        }
        if utterance_l.strip() in direct_followups:
            return True

        followup_markers = {
            "just",
            "small",
            "one",
            "that",
            "this",
            "it",
            "same",
            "little",
        }
        return any(token in followup_markers for token in words)

    def _context_suggests_chat_followup(self, utterance_l: str, chat_ctx: List[Any]) -> bool:
        if not chat_ctx or not self._looks_like_short_followup(utterance_l):
            return False
        last_assistant = self._last_assistant_message_text(chat_ctx)
        if not last_assistant:
            return False
        return bool(re.search(r"\?\s*$", last_assistant.strip()))

    @staticmethod
    def _legacy_route_action(route: str) -> Dict[str, Any]:
        route_key = str(route or "chat").strip().lower() or "chat"
        return {
            "type": route_key,
            "target": route_key,
            "tool": None,
            "arguments": {},
            "confidence": 0.5,
            "reason": "legacy_router_baseline",
        }

    async def _compute_shadow_action(
        self,
        *,
        utterance: str,
        chat_ctx: List[Any],
        legacy_route: str,
    ) -> tuple[Dict[str, Any], str]:
        prompt = (
            "You are Maya's routing shadow evaluator.\n"
            "Return exactly one JSON object with keys:\n"
            "type, target, tool, arguments, confidence, reason.\n"
            "Rules:\n"
            "- type must be one of identity, media_play, research, system, scheduling, chat\n"
            "- target must equal type\n"
            "- tool must be null unless type=system and a direct tool is explicit\n"
            "- arguments must be an object\n"
            "- confidence must be a float between 0 and 1\n"
            "- reason must be short\n"
            f"User message: {utterance}\n"
            f"Last assistant context: {self._last_assistant_message_text(chat_ctx)[:120]}\n"
            "JSON:"
        )
        try:
            response = await self._llm.chat(prompt, max_tokens=180, temperature=0.0)
            parsed = json.loads(str(response or "").strip())
            if not isinstance(parsed, dict):
                raise ValueError("shadow_not_object")
            action_type = str(parsed.get("type") or "").strip().lower()
            if action_type not in self.ALLOWED_KEYS:
                raise ValueError("shadow_type_invalid")
            confidence = float(parsed.get("confidence", 0.0))
            parsed["confidence"] = max(0.0, min(1.0, confidence))
            parsed["type"] = action_type
            parsed["target"] = str(parsed.get("target") or action_type).strip().lower()
            if parsed["target"] not in self.ALLOWED_KEYS:
                parsed["target"] = action_type
            parsed["arguments"] = dict(parsed.get("arguments") or {})
            parsed["tool"] = parsed.get("tool")
            parsed["reason"] = str(parsed.get("reason") or "shadow_llm")
            return parsed, "valid"
        except Exception as exc:
            logger.debug("agent_router_shadow_invalid error=%s", exc)
            return self._legacy_route_action(legacy_route), "shadow-invalid"

    async def _log_shadow_action(
        self,
        *,
        utterance: str,
        chat_ctx: List[Any],
        legacy_route: str,
    ) -> str:
        action, state = await self._compute_shadow_action(
            utterance=utterance,
            chat_ctx=chat_ctx,
            legacy_route=legacy_route,
        )
        logger.info(
            "agent_router_shadow legacy=%s state=%s action=%s",
            legacy_route,
            state,
            json.dumps(action, ensure_ascii=False),
        )
        if self._llm_router_active and state == "valid":
            return str(action.get("type") or legacy_route).strip().lower() or legacy_route
        return legacy_route

    async def _finalize_route(
        self,
        *,
        utterance: str,
        user_key: str,
        route: str,
        chat_ctx: List[Any],
        reason: str = "",
        confidence: float = 0.5,
        active_subject: str = "",
        last_route: str = "",
    ) -> str:
        chosen_route = str(route or "chat").strip().lower() or "chat"
        if self._llm_router_shadow:
            chosen_route = await self._log_shadow_action(
                utterance=utterance,
                chat_ctx=chat_ctx,
                legacy_route=chosen_route,
            )
        effective_last_route = str(last_route or self._last_route.get(user_key) or "").strip().lower()
        logger.info(
            "agent_router_decision text='%s' route=%s confidence=%.2f reason=%s last_route=%s active_subject=%s",
            str(utterance or "")[:60],
            chosen_route,
            max(0.0, min(1.0, float(confidence or 0.0))),
            reason or "unspecified",
            effective_last_route or "none",
            str(active_subject or "")[:80] or "none",
        )
        self._last_route[user_key] = chosen_route
        return chosen_route

    async def route(
        self,
        utterance: str,
        user_id: str,
        chat_ctx: List[Any] | None = None,
        recent_history: List[Any] | None = None,
        active_subject: str | None = None,
    ) -> str:
        user_key = str(user_id or "anonymous")
        self._pending_clarifications.pop(user_key, None)
        current = self._depth.get(user_key, 0)
        chat_ctx = list(chat_ctx or [])
        recent_history = list(recent_history or [])
        if current >= self.MAX_DEPTH:
            logger.warning("agent_depth_exceeded: %s at depth %s", user_key, current)
            self._depth[user_key] = 0
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route="chat",
                chat_ctx=chat_ctx,
                reason="depth_guard",
                confidence=1.0,
            )

        utterance_l = str(utterance or "").strip().lower()

        # 1. Deterministic overrides — run BEFORE LLM, no exceptions possible

        # Memory patterns take highest priority
        if any(re.search(pattern, utterance_l) for pattern in self._USER_MEMORY_PATTERNS):
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route="chat",
                chat_ctx=chat_ctx,
                reason="memory_query_pattern",
                confidence=0.96,
            )

        # Note operations should stay in chat tool path and never map to identity.
        if any(re.search(pattern, utterance_l) for pattern in self._NOTE_PATTERNS):
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route="chat",
                chat_ctx=chat_ctx,
                reason="note_pattern",
                confidence=0.95,
            )

        identity_hit = any(re.search(pattern, utterance_l) for pattern in self._IDENTITY_PATTERNS)
        research_intent_hit = any(re.search(pattern, utterance_l) for pattern in self._RESEARCH_INTENT_PATTERNS)
        system_intent_hit = any(re.search(pattern, utterance_l) for pattern in self._SYSTEM_INTENT_PATTERNS)

        # Identity patterns — second priority, unless explicit tool/system intent is present.
        if identity_hit and not (research_intent_hit or system_intent_hit):
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route="identity",
                chat_ctx=chat_ctx,
                reason="identity_pattern",
                confidence=0.95,
            )

        # Deterministic explicit research/system intents to avoid identity misrouting.
        if research_intent_hit:
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route="research",
                chat_ctx=chat_ctx,
                reason="research_intent_pattern",
                confidence=0.95,
            )

        if system_intent_hit:
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route="system",
                chat_ctx=chat_ctx,
                reason="system_intent_pattern",
                confidence=0.95,
            )

        # Greeting/smalltalk patterns — third priority
        if (
            re.search(r"^\s*(hi|hello|hey)\b", utterance_l)
            or "how are you" in utterance_l
            or re.search(r"\b(thanks|thank you)\b", utterance_l)
            or "tell me a joke" in utterance_l
        ):
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route="chat",
                chat_ctx=chat_ctx,
                reason="small_talk_pattern",
                confidence=0.95,
            )

        # Deterministic media/scheduling controls
        media_play_hit = any(re.search(pattern, utterance_l) for pattern in self._MEDIA_PLAY_PATTERNS)
        scheduling_hit = any(re.search(pattern, utterance_l) for pattern in self._SCHEDULING_PATTERNS)
        if media_play_hit and scheduling_hit:
            self._pending_clarifications[user_key] = (
                "I found multiple possible actions. Do you want media playback or scheduling?"
            )
            logger.info("agent_router_pending_clarification_set user=%s", user_key)
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route="chat",
                chat_ctx=chat_ctx,
                reason="media_scheduling_conflict",
                confidence=0.90,
            )
        if media_play_hit:
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route="media_play",
                chat_ctx=chat_ctx,
                reason="media_pattern",
                confidence=0.93,
            )

        task_list_hit = any(re.search(pattern, utterance_l) for pattern in self._TASK_LIST_PATTERNS)
        if task_list_hit:
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route="chat",
                chat_ctx=chat_ctx,
                reason="task_list_pattern",
                confidence=0.90,
            )

        if scheduling_hit:
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route="scheduling",
                chat_ctx=chat_ctx,
                reason="scheduling_pattern",
                confidence=0.93,
            )

        pronoun_followup_hit = any(
            re.search(pattern, utterance_l) for pattern in self._PRONOUN_FOLLOWUP_PATTERNS
        )
        if pronoun_followup_hit:
            resolved_subject = str(active_subject or "").strip() or self._resolve_subject_from_history(recent_history)
            if resolved_subject:
                return await self._finalize_route(
                    utterance=utterance,
                    user_key=user_key,
                    route="research",
                    chat_ctx=chat_ctx,
                    reason=f"pronoun_followup resolved_subject={resolved_subject[:80]}",
                    confidence=0.92,
                    active_subject=resolved_subject,
                )
            previous_route = self._last_route.get(user_key)
            if previous_route == "research":
                return await self._finalize_route(
                    utterance=utterance,
                    user_key=user_key,
                    route="research",
                    chat_ctx=chat_ctx,
                    reason="topic_continuation last_route=research",
                    confidence=0.85,
                )

        # Deterministic freshness/current-events research.
        # These queries should not block on the router LLM in console certification flows.
        # If route is research, run fact check to potentially down-route to chat.
        freshness_hit = any(re.search(pattern, utterance_l) for pattern in self._RESEARCH_FRESHNESS_PATTERNS)
        if freshness_hit:
            result = "research"
            leadership_query = bool(
                re.search(
                    r"\b(prime minister|chancellor|governor|mayor|president)\b",
                    utterance_l,
                )
            )
            conversational_leadership_query = leadership_query and bool(
                re.search(r"\b(do you know|tell me about|know about)\b", utterance_l)
            )
            if (not conversational_leadership_query) and await self._fact_classifier.is_simple_fact(utterance_l):
                result = "chat"
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route=result,
                chat_ctx=chat_ctx,
                reason="freshness_rule" if result == "research" else "simple_fact_override",
                confidence=0.90,
            )

        previous_route = self._last_route.get(user_key)
        if previous_route and self._is_ambiguous_followup_query(utterance_l):
            logger.info(
                "agent_router_decision_context_inherit: '%s' -> %s",
                str(utterance or "")[:50],
                previous_route,
            )
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route=previous_route,
                chat_ctx=chat_ctx,
                reason="ambiguous_followup_inherit",
                confidence=0.88,
                last_route=previous_route,
            )

        if self._context_suggests_chat_followup(utterance_l, chat_ctx):
            logger.info("agent_router_decision_context_followup: '%s' -> chat", str(utterance or "")[:50])
            return await self._finalize_route(
                utterance=utterance,
                user_key=user_key,
                route="chat",
                chat_ctx=chat_ctx,
                reason="chat_followup_context",
                confidence=0.84,
            )

        # 2. LLM handles everything else — research, system, media, ambiguous chat
        self._depth[user_key] = current + 1

        prompt = """You are the routing brain for Maya.
Given a user message, return ONLY the agent name.

AGENTS:
- identity    -> questions about Maya herself: who are you, what is your name, what can you do
- media_play  -> play music, play songs by X, put on some music, play [artist/album], spotify requests, or media control beyond basic fast-path controls
- research    -> search for, what is X, tell me about X, who made X, news about
- system      -> open file, move folder, take screenshot, close window, desktop ops
- scheduling  -> set, list, or delete reminders, alarms, or calendar events
- chat        -> greetings, small talk, follow-ups, math, jokes, and user-memory questions
                 such as "do you know my name" or "what do you know about me"

USER MESSAGE: "{utterance}"

Reply with ONLY one word: identity / media_play / research / system / scheduling / chat"""

        try:
            response = await self._llm.chat(
                prompt.format(utterance=utterance),
                max_tokens=10,
                temperature=0.0,
            )
            key = str(response or "").strip().lower().split()[0] if str(response or "").strip() else ""
            result = key if key in self.ALLOWED_KEYS else "chat"

            # Research freshness override still applies on non-protected LLM results.
            protected_intents = {"youtube", "media_play", "identity", "system"}
            if (
                result not in protected_intents
                and any(re.search(pattern, utterance_l) for pattern in self._RESEARCH_FRESHNESS_PATTERNS)
            ):
                result = "research"
            if result == "research":
                leadership_query = bool(
                    re.search(
                        r"\b(prime minister|chancellor|governor|mayor|president)\b",
                        utterance_l,
                    )
                )
                conversational_leadership_query = leadership_query and bool(
                    re.search(r"\b(do you know|tell me about|know about)\b", utterance_l)
                )
                if (not conversational_leadership_query) and await self._fact_classifier.is_simple_fact(utterance_l):
                    result = "chat"
        except Exception:
            result = "chat"
        finally:
            self._depth[user_key] = max(0, self._depth.get(user_key, 1) - 1)

        return await self._finalize_route(
            utterance=utterance,
            user_key=user_key,
            route=result,
            chat_ctx=chat_ctx,
            reason="llm_router",
            confidence=0.70 if result != "chat" else 0.60,
            active_subject=str(active_subject or "").strip(),
        )
