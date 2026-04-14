import logging
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
        r"\blist reminders\b",
        r"\bshow reminders\b",
        r"\bdelete reminder\b",
        r"\bset (?:an )?alarm\b",
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

    def __init__(self, llm_client: Any):
        self._llm = llm_client
        self._fact_classifier = FactClassifier(llm_client)
        self._depth: Dict[str, int] = {}
        self.MAX_DEPTH = 3
        self._last_route: Dict[str, str] = {}
        self._pending_clarifications: Dict[str, str] = {}

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

    async def route(self, utterance: str, user_id: str, chat_ctx: List[Any] | None = None) -> str:
        user_key = str(user_id or "anonymous")
        self._pending_clarifications.pop(user_key, None)
        current = self._depth.get(user_key, 0)
        if current >= self.MAX_DEPTH:
            logger.warning("agent_depth_exceeded: %s at depth %s", user_key, current)
            self._depth[user_key] = 0
            return "chat"

        utterance_l = str(utterance or "").strip().lower()
        chat_ctx = list(chat_ctx or [])

        # 1. Deterministic overrides — run BEFORE LLM, no exceptions possible

        # Memory patterns take highest priority
        if any(re.search(pattern, utterance_l) for pattern in self._USER_MEMORY_PATTERNS):
            result = "chat"
            self._last_route[user_key] = result
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        # Note operations should stay in chat tool path and never map to identity.
        if any(re.search(pattern, utterance_l) for pattern in self._NOTE_PATTERNS):
            result = "chat"
            self._last_route[user_key] = result
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        identity_hit = any(re.search(pattern, utterance_l) for pattern in self._IDENTITY_PATTERNS)
        research_intent_hit = any(re.search(pattern, utterance_l) for pattern in self._RESEARCH_INTENT_PATTERNS)
        system_intent_hit = any(re.search(pattern, utterance_l) for pattern in self._SYSTEM_INTENT_PATTERNS)

        # Identity patterns — second priority, unless explicit tool/system intent is present.
        if identity_hit and not (research_intent_hit or system_intent_hit):
            result = "identity"
            self._last_route[user_key] = result
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        # Deterministic explicit research/system intents to avoid identity misrouting.
        if research_intent_hit:
            result = "research"
            self._last_route[user_key] = result
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        if system_intent_hit:
            result = "system"
            self._last_route[user_key] = result
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        # Greeting/smalltalk patterns — third priority
        if (
            re.search(r"^\s*(hi|hello|hey)\b", utterance_l)
            or "how are you" in utterance_l
            or re.search(r"\b(thanks|thank you)\b", utterance_l)
            or "tell me a joke" in utterance_l
        ):
            result = "chat"
            self._last_route[user_key] = result
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        # Deterministic media/scheduling controls
        media_play_hit = any(re.search(pattern, utterance_l) for pattern in self._MEDIA_PLAY_PATTERNS)
        scheduling_hit = any(re.search(pattern, utterance_l) for pattern in self._SCHEDULING_PATTERNS)
        if media_play_hit and scheduling_hit:
            result = "chat"
            self._pending_clarifications[user_key] = (
                "I found multiple possible actions. Do you want media playback or scheduling?"
            )
            self._last_route[user_key] = result
            logger.info("agent_router_pending_clarification_set user=%s", user_key)
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result
        if media_play_hit:
            result = "media_play"
            self._last_route[user_key] = result
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        task_list_hit = any(re.search(pattern, utterance_l) for pattern in self._TASK_LIST_PATTERNS)
        if task_list_hit:
            result = "chat"
            self._last_route[user_key] = result
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        if scheduling_hit:
            result = "scheduling"
            self._last_route[user_key] = result
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        # Deterministic freshness/current-events research.
        # These queries should not block on the router LLM in console certification flows.
        # If route is research, run fact check to potentially down-route to chat.
        freshness_hit = any(re.search(pattern, utterance_l) for pattern in self._RESEARCH_FRESHNESS_PATTERNS)
        if freshness_hit:
            result = "research"
            if await self._fact_classifier.is_simple_fact(utterance_l):
                result = "chat"
            self._last_route[user_key] = result
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return result

        previous_route = self._last_route.get(user_key)
        if previous_route and self._is_ambiguous_followup_query(utterance_l):
            self._last_route[user_key] = previous_route
            logger.info(
                "agent_router_decision_context_inherit: '%s' -> %s",
                str(utterance or "")[:50],
                previous_route,
            )
            return previous_route

        if self._context_suggests_chat_followup(utterance_l, chat_ctx):
            result = "chat"
            self._last_route[user_key] = result
            logger.info("agent_router_decision_context_followup: '%s' -> %s", str(utterance or "")[:50], result)
            return result

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
                if await self._fact_classifier.is_simple_fact(utterance_l):
                    result = "chat"
        except Exception:
            result = "chat"
        finally:
            self._depth[user_key] = max(0, self._depth.get(user_key, 1) - 1)

        logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
        self._last_route[user_key] = result
        return result
