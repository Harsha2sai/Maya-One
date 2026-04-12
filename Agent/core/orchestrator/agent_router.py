import logging
import re
from typing import Any, Dict, List

from core.action.precedence import RoutePrecedenceResolver, RouteCandidate
from core.action.constants import RoutePrecedence

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
        r"\bgoogle\b",
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
        self._depth: Dict[str, int] = {}
        self.MAX_DEPTH = 3
        self._pending_clarification: Dict[str, str] = {}
        self._last_route: Dict[str, str] = {}

    def consume_pending_clarification(self, user_id: str) -> str | None:
        """Consume and return any pending clarification message for the user."""
        result = self._pending_clarification.get(user_id)
        self._pending_clarification[user_id] = None
        return result

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
            "reason",
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
        current = self._depth.get(user_key, 0)
        if current >= self.MAX_DEPTH:
            logger.warning("agent_depth_exceeded: %s at depth %s", user_key, current)
            self._depth[user_key] = 0
            return "chat"

        utterance_l = str(utterance or "").strip().lower()
        chat_ctx = list(chat_ctx or [])

        # Helper to store and return
        def store_and_return(route: str) -> str:
            self._last_route[user_key] = route
            return route

        # 0. Handle ambiguous followups that should inherit previous route
        # This runs first to allow context inheritance before other checks
        if self._looks_like_short_followup(utterance_l):
            previous_route = self._last_route.get(user_key)
            if previous_route:
                logger.info("agent_router_decision_followup_inherits: '%s' -> %s", str(utterance or "")[:50], previous_route)
                self._last_route[user_key] = previous_route
                return previous_route

        # 1. Deterministic overrides — run BEFORE LLM, no exceptions possible

        # Memory patterns take highest priority
        if any(re.search(pattern, utterance_l) for pattern in self._USER_MEMORY_PATTERNS):
            result = "chat"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return store_and_return(result)

        # Note operations should stay in chat tool path and never map to identity.
        if any(re.search(pattern, utterance_l) for pattern in self._NOTE_PATTERNS):
            result = "chat"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return store_and_return(result)

        identity_hit = any(re.search(pattern, utterance_l) for pattern in self._IDENTITY_PATTERNS)
        research_intent_hit = any(re.search(pattern, utterance_l) for pattern in self._RESEARCH_INTENT_PATTERNS)
        system_intent_hit = any(re.search(pattern, utterance_l) for pattern in self._SYSTEM_INTENT_PATTERNS)

        # Identity patterns — second priority, unless explicit tool/system intent is present.
        if identity_hit and not (research_intent_hit or system_intent_hit):
            result = "identity"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return store_and_return(result)

        # Deterministic explicit research/system intents to avoid identity misrouting.
        if research_intent_hit:
            result = "research"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return store_and_return(result)

        if system_intent_hit:
            result = "system"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return store_and_return(result)

        # Greeting/smalltalk patterns — third priority
        if (
            re.search(r"^\s*(hi|hello|hey)\b", utterance_l)
            or "how are you" in utterance_l
            or re.search(r"\b(thanks|thank you)\b", utterance_l)
            or "tell me a joke" in utterance_l
        ):
            result = "chat"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return store_and_return(result)

        # Deterministic media controls - defer return until after conflict check
        media_play_hit = any(re.search(pattern, utterance_l) for pattern in self._MEDIA_PLAY_PATTERNS)

        task_list_hit = any(re.search(pattern, utterance_l) for pattern in self._TASK_LIST_PATTERNS)
        if task_list_hit:
            result = "chat"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return store_and_return(result)

        scheduling_hit = any(re.search(pattern, utterance_l) for pattern in self._SCHEDULING_PATTERNS)
        freshness_hit = any(re.search(pattern, utterance_l) for pattern in self._RESEARCH_FRESHNESS_PATTERNS)

        # Check for conflicts between tool intents at same precedence level
        # Note: media_play vs freshness should not trigger conflict - media_play wins
        resolver = RoutePrecedenceResolver()
        candidates = []
        # Only check scheduling vs freshness conflicts (not media_play)
        if scheduling_hit:
            candidates.append(RouteCandidate(route="scheduling", precedence=RoutePrecedence.LLM_TOOL_DETERMINISTIC, target="schedule"))
        if freshness_hit:
            candidates.append(RouteCandidate(route="research", precedence=RoutePrecedence.LLM_TOOL_DETERMINISTIC, target="research"))
        # Media_play conflicts only with scheduling (add it only if scheduling also hits)
        if media_play_hit and scheduling_hit:
            candidates.append(RouteCandidate(route="media_play", precedence=RoutePrecedence.LLM_TOOL_DETERMINISTIC, target="media"))

        if len(candidates) > 1:
            resolution = resolver.resolve(candidates)
            if resolution.ask_clarification:
                self._pending_clarification[user_key] = "multiple possible actions detected"
                result = "chat"
                logger.info("agent_router_decision_conflict: '%s' -> %s", str(utterance or "")[:50], result)
                return store_and_return(result)
            result = resolution.route
            logger.info("agent_router_decision_resolved: '%s' -> %s", str(utterance or "")[:50], result)
            return store_and_return(result)

        # No conflicts - proceed with individual returns
        if media_play_hit:
            result = "media_play"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return store_and_return(result)

        if scheduling_hit:
            result = "scheduling"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return store_and_return(result)

        if freshness_hit:
            result = "research"
            logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
            return store_and_return(result)

        if self._context_suggests_chat_followup(utterance_l, chat_ctx):
            result = "chat"
            logger.info("agent_router_decision_context_followup: '%s' -> %s", str(utterance or "")[:50], result)
            return store_and_return(result)

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
        except Exception:
            result = "chat"
        finally:
            self._depth[user_key] = max(0, self._depth.get(user_key, 1) - 1)

        logger.info("agent_router_decision: '%s' -> %s", str(utterance or "")[:50], result)
        return store_and_return(result)
